#!/usr/bin/env python3
"""Evaluation of offset-aware loop fusion in Polly (see README.md).

For every kernel and configuration:
  1. build the kernel with -mllvm -stats, as LLVM IR, and with the Polly
     run-time check print (-polly-codegen-emit-rtc-print);
  2. compare the checksums of `driver check` bit-exactly with plain -O3;
  3. check that Polly code exists in the IR and that the run-time check
     succeeds at run time, i.e. that the optimized code is really executed;
  4. check the kernel's `// EXPECT <config>: ...` lines;
  5. optionally benchmark it.
Exits with status 1 if any check fails.
"""
import argparse
import concurrent.futures
import csv
import datetime
import os
import re
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

POLLY = ["-mllvm", "-polly", "-mllvm", "-polly-process-unprofitable"]
OFFSET = POLLY + ["-mllvm", "-polly-force-offset-fusion"]
CONFIGS = {
    "O3": [],
    "polly": POLLY,
    "greedy": POLLY + ["-mllvm", "-polly-loopfusion-greedy"],
    "offset": OFFSET,
    "noprox": OFFSET + ["-mllvm", "-polly-offset-fusion-proximity=0"],
    "noshift": OFFSET + ["-mllvm", "-polly-offset-fusion-shift=0"],
    "noiso": OFFSET + ["-mllvm", "-polly-offset-fusion-isolate=0"],
    "aligned": OFFSET + ["-mllvm", "-polly-offset-fusion-prefer-aligned"],
    "unserialize": OFFSET + ["-mllvm", "-polly-offset-fusion-unserialize"],
}

STATS = {
    "Number of greedy fusions with a constant shift": "shifted",
    "Number of greedy fusions without shift": "plain",
    "Number of fused bands with isolated interior": "isolated",
    "Number of statement pairs linked by offset proximity": "proximity",
    "Number of statements with a recovered logical offset": "offsets",
}
STAT_KEYS = ["offsets", "proximity", "plain", "shifted", "isolated"]

# Sizes from which the run-time check must succeed in `driver check`. Smaller
# sizes may legitimately take the original code (e.g. the kernels' early
# returns, or run-time checks that fail for tiny n).
MIN_RTC_SIZE = 17

RTC_RE = re.compile(r"F: (\S+) R: .*RTC: (-?\d+) Overflow: (-?\d+)")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def parse_expectations(path, config):
    """Tokens of `// EXPECT <config>: tok tok ...` for @p config, where <config>
    may be `*` for all Polly configurations. A token is <stat><op><int>
    (stat: offsets, proximity, plain, shifted, fused, isolated; op: >=, ==, <=),
    `polly` (the optimized code is executed) or `nopolly` (it is known not to
    be executed)."""
    toks = []
    for line in open(path):
        m = re.match(r"\s*//\s*EXPECT\s+(\S+):\s*(.*)$", line)
        if m and (m.group(1) == config or (m.group(1) == "*" and config != "O3")):
            toks.extend(m.group(2).split())
    return toks


def check_token(tok, stats, polly_ok):
    if tok == "polly":
        return polly_ok
    if tok == "nopolly":
        return not polly_ok
    m = re.fullmatch(r"(\w+)(>=|==|<=)(\d+)", tok)
    if not m:
        return False
    key, op, val = m.group(1), m.group(2), int(m.group(3))
    have = stats["plain"] + stats["shifted"] if key == "fused" else stats[key]
    return {">=": have >= val, "==": have == val, "<=": have <= val}[op]


def parse_check_output(out):
    """Returns {n: hash} and {n: (num kernel RTC prints, num successful)}."""
    hashes, rtc, pending = {}, {}, []
    for line in out.splitlines():
        m = RTC_RE.search(line)
        if m:
            if m.group(1) == "kernel_impl":
                pending.append(m.group(2) == "-1" and m.group(3) == "-1")
            continue
        m = re.match(r"n=(\d+) ([0-9a-f]+)$", line)
        if m:
            n = int(m.group(1))
            hashes[n] = m.group(2)
            rtc[n] = (len(pending), sum(pending))
            pending = []
    return hashes, rtc


class Build:
    def __init__(self, kernel, config, outdir, args):
        self.kernel, self.config = kernel, config
        self.dir = os.path.join(outdir, "build", kernel, config)
        self.src = os.path.join(HERE, "kernels", kernel + ".cpp")
        self.flags = ["-O3", "-std=c++17"] + args.cflags + CONFIGS[config]
        self.args = args
        self.bin = os.path.join(self.dir, "bin")
        self.bin_rtc = os.path.join(self.dir, "bin_rtc")
        self.stats = {k: 0 for k in STAT_KEYS}
        self.polly_blocks = 0
        self.nopolly = False

    @property
    def uses_polly(self):
        return self.config != "O3"

    def run(self, driver_obj):
        os.makedirs(self.dir, exist_ok=True)
        cxx = self.args.clang
        obj = os.path.join(self.dir, "kernel.o")
        r = sh([cxx] + self.flags + ["-mllvm", "-stats", "-c", self.src, "-o", obj])
        open(os.path.join(self.dir, "build.log"), "w").write(r.stderr)
        if r.returncode:
            return "compile failed:\n" + r.stderr
        for line in r.stderr.splitlines():
            m = re.match(r"\s*(\d+) \S+\s+- (.*?)\s*$", line)
            if m and m.group(2) in STATS:
                self.stats[STATS[m.group(2)]] = int(m.group(1))
        ir = os.path.join(self.dir, "kernel.ll")
        r = sh([cxx] + self.flags + ["-S", "-emit-llvm", self.src, "-o", ir])
        if r.returncode:
            return "IR emission failed:\n" + r.stderr
        # Blocks of Polly's optimized code version. -O3 may merge or rename the
        # polly.stmt.* blocks, so accept any of these. polly.split_new_and_old
        # is not included: it also exists if the run-time check is `false`.
        self.polly_blocks = sum(
            1 for l in open(ir)
            if re.match(r"polly\.(stmt|loop_\w+|cond|merge|then|else)[\w.]*:", l))
        r = sh([cxx, obj, driver_obj, "-o", self.bin])
        if r.returncode:
            return "link failed:\n" + r.stderr
        if self.uses_polly:
            obj_rtc = os.path.join(self.dir, "kernel_rtc.o")
            r = sh([cxx] + self.flags + ["-mllvm", "-polly-codegen-emit-rtc-print",
                                         "-c", self.src, "-o", obj_rtc])
            if r.returncode:
                return "RTC build failed:\n" + r.stderr
            r = sh([cxx, obj_rtc, driver_obj, "-o", self.bin_rtc])
            if r.returncode:
                return "RTC link failed:\n" + r.stderr
        return None


def pick_cpu():
    """The CPU with the highest maximal frequency (a P-core on hybrid CPUs),
    avoiding CPU 0."""
    best, best_f = None, -1
    for c in range(1, os.cpu_count() or 1):
        try:
            f = int(open(f"/sys/devices/system/cpu/cpu{c}/cpufreq/cpuinfo_max_freq").read())
        except OSError:
            continue
        if f > best_f:
            best, best_f = c, f
    return best if best is not None else 0


def perf_usable():
    if not shutil.which("perf"):
        return False
    r = sh(["perf", "stat", "-x,", "-e", "cache-misses", "true"])
    return r.returncode == 0 and "not supported" not in r.stderr


def read_file(path, default="?"):
    try:
        return open(path).read().strip()
    except OSError:
        return default


def main():
    kernels_all = sorted(f[:-4] for f in os.listdir(os.path.join(HERE, "kernels"))
                         if f.endswith(".cpp"))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kernels", default=",".join(kernels_all),
                    help="comma-separated kernel names (default: all)")
    ap.add_argument("--configs", default=",".join(CONFIGS),
                    help="comma-separated configurations (default: all)")
    ap.add_argument("--sizes", default="1024,16384,262144,4194304,16777216",
                    help="benchmark sizes (elements per array)")
    ap.add_argument("--reps", type=int, default=11, help="benchmark repetitions")
    ap.add_argument("--no-bench", action="store_true", help="only check correctness")
    ap.add_argument("--perf", action="store_true",
                    help="also record cache misses with perf stat")
    ap.add_argument("--cpu", type=int, default=None, help="CPU to pin benchmarks to")
    ap.add_argument("--clang", default=os.path.join(REPO, "build", "bin", "clang++"))
    ap.add_argument("--cflags", default="", help="extra compiler flags, e.g. -march=native")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--out", default=None, help="output directory")
    args = ap.parse_args()
    args.cflags = args.cflags.split()

    kernels = args.kernels.split(",")
    configs = args.configs.split(",")
    for c in configs:
        if c not in CONFIGS:
            fail(f"unknown configuration {c}")
    if "O3" not in configs:
        configs.insert(0, "O3")  # The reference for all comparisons.
    for k in kernels:
        if k not in kernels_all:
            fail(f"unknown kernel {k}")
    sizes = [int(s) for s in args.sizes.split(",")]
    cpu = pick_cpu() if args.cpu is None else args.cpu
    if args.perf and not perf_usable():
        fail("perf stat is not usable; try `sudo sysctl kernel.perf_event_paranoid=1`")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = args.out or os.path.join(HERE, "results", stamp)
    os.makedirs(outdir, exist_ok=True)

    governor = read_file(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
    meta = {
        "date": stamp,
        "clang": sh([args.clang, "--version"]).stdout.splitlines()[0],
        "git": sh(["git", "-C", REPO, "rev-parse", "--short", "HEAD"]).stdout.strip(),
        "cpu": f"{cpu} ({read_file('/proc/cpuinfo', '').split('model name')[1].split(':')[1].splitlines()[0].strip() if 'model name' in read_file('/proc/cpuinfo', '') else '?'})",
        "governor": governor,
        "cflags": " ".join(args.cflags),
        "reps": args.reps,
    }
    with open(os.path.join(outdir, "meta.txt"), "w") as f:
        for k, v in meta.items():
            f.write(f"{k}: {v}\n")
    if not args.no_bench and governor != "performance":
        print(f"warning: CPU {cpu} uses the '{governor}' governor; timings will be noisy "
              "(`sudo cpupower frequency-set -g performance`)", file=sys.stderr)

    # 1. Build.
    driver_obj = os.path.join(outdir, "build", "driver.o")
    os.makedirs(os.path.dirname(driver_obj), exist_ok=True)
    r = sh([args.clang, "-O3", "-std=c++17", "-c", os.path.join(HERE, "driver.cpp"),
            "-o", driver_obj])
    if r.returncode:
        fail("driver build failed:\n" + r.stderr)
    builds = {(k, c): Build(k, c, outdir, args) for k in kernels for c in configs}
    print(f"building {len(builds)} kernel/configuration pairs...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
        errors = dict(zip(builds, ex.map(lambda b: b.run(driver_obj), builds.values())))
    for key, err in errors.items():
        if err:
            fail(f"{key[0]}/{key[1]}: {err}")

    # 2.-4. Correctness, Polly path, expectations.
    problems = []
    rows = []
    for k in kernels:
        ref, _ = parse_check_output(sh([builds[(k, "O3")].bin, "check"]).stdout)
        for c in configs:
            b = builds[(k, c)]
            hashes, _ = parse_check_output(sh([b.bin, "check"]).stdout)
            mismatch = sorted(n for n in ref if hashes.get(n) != ref[n])
            if mismatch:
                problems.append(f"{k}/{c}: result differs from O3 for n={mismatch}")
            polly_sizes = []
            if b.uses_polly:
                _, rtc = parse_check_output(sh([b.bin_rtc, "check"]).stdout)
                polly_sizes = [n for n, (cnt, ok) in sorted(rtc.items()) if cnt and ok == cnt]
            polly_ok = (b.polly_blocks > 0 and
                        all(n in polly_sizes for n in ref if n >= MIN_RTC_SIZE))
            expect = parse_expectations(b.src, c)
            b.nopolly = "nopolly" in expect
            for tok in expect:
                if not check_token(tok, b.stats, polly_ok):
                    problems.append(f"{k}/{c}: expectation `{tok}` failed "
                                    f"(stats {b.stats}, polly code: {polly_ok})")
            rows.append({"kernel": k, "config": c, **b.stats,
                         "polly_blocks": b.polly_blocks,
                         "polly_path_sizes": " ".join(map(str, polly_sizes)),
                         "polly_ok": int(polly_ok) if b.uses_polly else "",
                         "matches_O3": int(not mismatch)})
    with open(os.path.join(outdir, "correctness.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # 5. Benchmarks.
    bench = []
    if not args.no_bench:
        for k in kernels:
            for c in configs:
                b = builds[(k, c)]
                for n in sizes:
                    # The optimized code must be used at this size (section 9.3).
                    path_ok = True
                    if b.uses_polly:
                        out = sh([b.bin_rtc, "bench", str(n), "0"]).stdout
                        prints = [m for m in RTC_RE.finditer(out) if m.group(1) == "kernel_impl"]
                        path_ok = bool(prints) and all(
                            m.group(2) == "-1" and m.group(3) == "-1" for m in prints)
                    cmd = ["taskset", "-c", str(cpu), b.bin, "bench", str(n), str(args.reps)]
                    row = {"kernel": k, "config": c, "n": n}
                    if args.perf:
                        cmd = ["perf", "stat", "-x,", "-e",
                               "cache-misses,L1-dcache-load-misses"] + cmd
                    r = sh(cmd)
                    m = re.search(r"median_ns=(\d+) min_ns=(\d+)", r.stdout)
                    if not m:
                        fail(f"{k}/{c}: benchmark failed:\n{r.stdout}{r.stderr}")
                    row["median_ns"] = int(m.group(1))
                    row["min_ns"] = int(m.group(2))
                    row["ns_per_elem"] = round(int(m.group(1)) / max(n, 1), 4)
                    if args.perf:
                        # Counters cover all REPS + 1 runs and the initialization.
                        for line in r.stderr.splitlines():
                            parts = line.split(",")
                            if len(parts) > 2 and parts[2] in ("cache-misses",
                                                               "L1-dcache-load-misses"):
                                row[parts[2]] = parts[0]
                    row["polly_path"] = int(path_ok) if b.uses_polly else ""
                    if b.uses_polly and not path_ok and not b.nopolly:
                        problems.append(f"{k}/{c}: Polly code not executed at n={n}")
                    bench.append(row)
                    print(f"  {k:18s} {c:12s} n={n:<9d} {row['ns_per_elem']:.3f} ns/elem",
                          file=sys.stderr)
        fields = ["kernel", "config", "n", "median_ns", "min_ns", "ns_per_elem", "polly_path"]
        if args.perf:
            fields += ["cache-misses", "L1-dcache-load-misses"]
        with open(os.path.join(outdir, "bench.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(bench)

    write_summary(outdir, meta, kernels, configs, sizes, rows, bench, problems)
    print(open(os.path.join(outdir, "summary.md")).read())
    if problems:
        print(f"\n{len(problems)} problem(s), see {outdir}/summary.md", file=sys.stderr)
        sys.exit(1)
    print(f"all checks passed; results in {outdir}", file=sys.stderr)


def write_summary(outdir, meta, kernels, configs, sizes, rows, bench, problems):
    L = ["# Offset-aware fusion evaluation", ""]
    L += [f"- {k}: {v}" for k, v in meta.items()]
    L += ["", "## Problems", ""]
    L += [f"- {p}" for p in problems] or ["None."]
    L += ["", "## Transformations (from -stats) and Polly path", "",
          "offsets / proximity pairs / plain fusions / shifted fusions / isolated bands; "
          "`!` = optimized code not (always) executed, `X` = wrong result", ""]
    L.append("| kernel | " + " | ".join(configs) + " |")
    L.append("|---" * (len(configs) + 1) + "|")
    by = {(r["kernel"], r["config"]): r for r in rows}
    for k in kernels:
        cells = []
        for c in configs:
            r = by[(k, c)]
            cell = "-" if c == "O3" else "/".join(str(r[s]) for s in STAT_KEYS)
            if c != "O3" and not r["polly_ok"]:
                cell += " !"
            if not r["matches_O3"]:
                cell += " X"
            cells.append(cell)
        L.append(f"| {k} | " + " | ".join(cells) + " |")
    if bench:
        L += ["", "## Speedup over O3 (median time, higher is better)", ""]
        bb = {(r["kernel"], r["config"], r["n"]): r for r in bench}
        for n in sizes:
            L += [f"### n = {n}", ""]
            L.append("| kernel | O3 ns/elem | " + " | ".join(c for c in configs if c != "O3") + " |")
            L.append("|---" * (len(configs) + 1) + "|")
            for k in kernels:
                base = bb[(k, "O3", n)]["median_ns"]
                cells = []
                for c in configs:
                    if c == "O3":
                        continue
                    r = bb[(k, c, n)]
                    cell = f"{base / r['median_ns']:.2f}" if r["median_ns"] else "?"
                    if r["polly_path"] == 0:
                        cell += " !"
                    cells.append(cell)
                L.append(f"| {k} | {bb[(k, 'O3', n)]['ns_per_elem']:.3f} | " + " | ".join(cells) + " |")
            L.append("")
        geo = []
        for c in configs:
            if c == "O3":
                continue
            ratios = [bb[(k, "O3", n)]["median_ns"] / bb[(k, c, n)]["median_ns"]
                      for k in kernels for n in sizes if bb[(k, c, n)]["median_ns"]]
            geo.append(f"{c}: {statistics.geometric_mean(ratios):.3f}")
        L += ["Geometric mean speedup over all kernels and sizes: " + ", ".join(geo), ""]
    open(os.path.join(outdir, "summary.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
