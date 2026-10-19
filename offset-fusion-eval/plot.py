#!/usr/bin/env python3
"""Figures for an offset-fusion evaluation run (see README.md).

    .venv/bin/python plot.py [RESULTS_DIR] [--cache-size N] [--format png,svg]

RESULTS_DIR defaults to the newest directory in results/. The figures and a
table view (speedup.csv) are written to RESULTS_DIR/figures/:

  fig1_speedup_vs_size   speedup over O3 per kernel and array size
  fig2_speedup_largest   speedup over O3 per kernel at the largest size
  fig3_ablation          speedup of every configuration, cache-resident vs
                         memory-bound size (heatmaps)
  fig4_geomean           geometric-mean speedup per configuration
  sweep/<kernel>         per kernel: speedup over O3 by array size for all
                         configurations, with cache boundaries and the
                         run-to-run spread (for dense `run.py --sizes sweep`)

Speedup = median time of O3 / median time of the configuration; > 1 is
faster than O3. With `run.py --runs N`, the time of each benchmark is the
median over the N runs. Configurations whose optimized code is not executed
(the kernel falls back to the original code) are marked, and left out of the
geometric means.
"""
import argparse
import csv
import math
import os
import re
import statistics
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# Reference palette (dataviz skill, light mode). The three series colors were
# validated as an adjacent categorical set.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = {  # Fixed per configuration, never by rank.
    "offset": ("#2a78d6", "o"),
    "greedy": ("#eb6834", "s"),
    "aligned": ("#1baf7a", "D"),
    "polly": ("#eda100", "v"),
    "noprox": ("#e87ba4", "^"),
    "noshift": ("#008300", "P"),
    "noiso": ("#6250d6", "X"),
    "unserialize": ("#e34948", "*"),
}
# Series of fig1 (the overview), and of the two panels of the per-kernel sweep
# figures. Each set was checked with the dataviz palette validator (adjacent
# pairs, light surface): slots 1-4 and slots 1, 5-8 of the reference palette.
OVERVIEW_SERIES = ("offset", "greedy", "aligned")
SWEEP_MAIN = ("polly", "greedy", "offset", "aligned")
SWEEP_ABLATION = ("offset", "noprox", "noshift", "noiso", "unserialize")
LABELS = {
    "O3": "O3 (no Polly)",
    "polly": "Polly",
    "greedy": "Polly + greedy fusion",
    "offset": "offset-aware fusion",
    "noprox": "offset, no proximity",
    "noshift": "offset, no shift",
    "noiso": "offset, no isolation",
    "aligned": "offset, prefer aligned",
    "unserialize": "offset, unserialized isl",
}
KERNEL_TITLES = {
    "k01_shifted": "k01 · diploma example",
    "k02_three": "k02 · 3 loops, same range",
    "k03_pair": "k03 · misaligned pair",
    "k04_stl3": "k04 · 3× transform",
    "k05_stl3_vec": "k05 · 3× transform, vector",
    "k06_chain2_off2": "k06 · 2× transform, +2",
    "k07_chain4_mixed": "k07 · 4× transform, mixed",
    "k08_chain6": "k08 · 6× transform",
    "k09_algos": "k09 · iota/replace_if/for_each",
    "k10_binary": "k10 · unary + binary",
    "k11_maxshift": "k11 · offset 10 (not fused)",
}
# Diverging scale for speedups: red = slower, gray = equal, blue = faster.
DIVERGING = LinearSegmentedColormap.from_list(
    "speedup", ["#a3302f", "#e34948", "#f3b3ad", "#f0efec", "#9ec5f4", "#3987e5", "#184f95"])


def style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 9,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK_2,
        "axes.titlesize": 9,
        "axes.titlecolor": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "grid.linestyle": "-",
        "legend.frameon": False,
        "text.color": INK,
    })


def fmt_size(n):
    for unit, div in (("M", 1 << 20), ("K", 1 << 10)):
        if n >= div and n % div == 0:
            return f"{n // div}{unit}"
    return str(n)


def load_runs(results):
    """{(kernel, config, n): {run: median_ns}} and the metadata. Results without
    a `run` column (a single run) count as run 0."""
    bench = list(csv.DictReader(open(os.path.join(results, "bench.csv"))))
    meta = {}
    for line in open(os.path.join(results, "meta.txt")):
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    times = {}
    for r in bench:
        key = (r["kernel"], r["config"], int(r["n"]))
        times.setdefault(key, {})[int(r.get("run") or 0)] = int(r["median_ns"])
    ok = {(r["kernel"], r["config"], int(r["n"])): r["polly_path"] != "0" for r in bench}
    return bench, times, ok, meta


def load(results):
    bench, times, ok, meta = load_runs(results)
    kernels = list(dict.fromkeys(r["kernel"] for r in bench))
    configs = list(dict.fromkeys(r["config"] for r in bench))
    sizes = sorted({int(r["n"]) for r in bench})
    t = {key: statistics.median(runs.values()) for key, runs in times.items()}
    speedup = {}
    for (k, c, n), v in t.items():
        base = t.get((k, "O3", n))
        if base and v:
            speedup[(k, c, n)] = base / v
    return kernels, configs, sizes, speedup, ok, meta


def run_speedups(times, k, c, n):
    """Speedups over O3 of the individual runs (O3 of the same run)."""
    base = times.get((k, "O3", n), {})
    return [base[r] / v for r, v in times.get((k, c, n), {}).items() if r in base and v]


def subtitle(meta):
    cpu = meta.get("cpu", "?")
    num, _, model = cpu.partition(" (")
    model = model.rstrip(")").replace("12th Gen Intel(R) Core(TM) ", "")
    runs = int(meta.get("runs", 1) or 1)
    reps = f"median of {meta.get('reps', '?')} runs"
    if runs > 1:
        reps = f"median of {meta.get('reps', '?')} repetitions, median over {runs} " \
               f"interleaved runs"
    s = f"{model or '?'}, pinned to CPU {num}, governor {meta.get('governor', '?')}, " \
        f"{reps}, commit {meta.get('git', '?')}"
    if meta.get("governor") != "performance":
        s = "Preliminary (not the performance governor): " + s
    return s


def header(fig, title, sub):
    """Title and subtitle in a band above the axes (leave it free via tight_layout's
    rect or subplots_adjust)."""
    fig.text(0.01, 0.99, title, fontsize=12, fontweight="semibold", color=INK,
             ha="left", va="top")
    width = int(fig.get_figwidth() * 15)  # Characters that fit at 8.5 pt.
    fig.text(0.01, 0.955, "\n".join(textwrap.wrap(sub, width)), fontsize=8.5,
             color=INK_2, ha="left", va="top", linespacing=1.4)


def save(fig, outdir, name, formats):
    for f in formats:
        fig.savefig(os.path.join(outdir, f"{name}.{f}"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def size_ticks(ax, sizes):
    """Log2 x axis over the array sizes. A dense sweep gets ticks at the powers
    of four only."""
    ax.set_xscale("log", base=2)
    ticks = sizes
    if len(sizes) > 8:
        ticks = [1 << e for e in range(0, 40, 2) if sizes[0] <= 1 << e <= sizes[-1]]
    ax.set_xticks(ticks)
    ax.set_xticklabels([fmt_size(n) for n in ticks])
    ax.minorticks_off()
    ax.set_xlim(sizes[0] / 1.15, sizes[-1] * 1.15)


def size_range(ns):
    if len(ns) > 4:
        return f"{fmt_size(ns[0])}–{fmt_size(ns[-1])}"
    return ", ".join(fmt_size(n) for n in ns)


def log_speedup_axis(ax, lo, hi):
    ax.set_yscale("log", base=2)
    ticks = [t for t in (1 / 32, 1 / 16, 0.125, 0.25, 0.5, 1, 2, 4, 8) if lo <= t <= hi]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}×" if t >= 0.125 else f"1/{round(1 / t)}×" for t in ticks])
    ax.minorticks_off()
    ax.set_ylim(lo, hi)


def fig_speedup_vs_size(kernels, sizes, speedup, ok, meta, outdir, formats):
    series = [c for c in OVERVIEW_SERIES if any((k, c, sizes[0]) in speedup for k in kernels)]
    dense = len(sizes) > 8
    ncols = 4
    nrows = math.ceil((len(kernels) + 1) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 2.35 * nrows + 0.6),
                             sharex=True, sharey=True)
    axes = axes.flatten()
    vals = [v for (k, c, n), v in speedup.items() if c in series]
    lo = 2 ** math.floor(math.log2(min(vals + [0.5])))
    hi = 2 ** math.ceil(math.log2(max(vals + [2.0])))
    for ax, k in zip(axes, kernels):
        ax.grid(True, axis="y")
        ax.axhline(1.0, color=INK_2, linewidth=1.0, zorder=1)
        for c in reversed(series):  # The subject series (offset) on top.
            color, marker = SERIES[c]
            xs = [n for n in sizes if (k, c, n) in speedup]
            ys = [speedup[(k, c, n)] for n in xs]
            ax.plot(xs, ys, color=color, linewidth=1.6 if dense else 2,
                    marker=None if dense else marker, markersize=5,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3,
                    solid_capstyle="round", solid_joinstyle="round")
        title = KERNEL_TITLES.get(k, k)
        ax.set_title(title, loc="left", fontweight="semibold")
        if any(not ok.get((k, c, n), True) for c in series for n in sizes):
            ax.text(0.02, 0.04, "optimized code not executed", transform=ax.transAxes,
                    color=MUTED, fontsize=8)
        size_ticks(ax, sizes)
        log_speedup_axis(ax, lo, hi)
    for ax in axes[len(kernels):]:
        ax.axis("off")
    # Legend in the first free panel.
    leg_ax = axes[len(kernels)]
    handles = [Line2D([], [], color=SERIES[c][0], marker=None if dense else SERIES[c][1],
                      linewidth=2, markersize=6, markeredgecolor=SURFACE, label=LABELS[c])
               for c in series]
    handles.append(Line2D([], [], color=INK_2, linewidth=1.0, label="O3 = 1×"))
    leg_ax.legend(handles=handles, loc="center left", fontsize=9, labelcolor=INK)
    for ax in axes[(nrows - 1) * ncols:]:
        if ax.get_visible():
            ax.set_xlabel("elements per array (4 B each)")
    for r in range(nrows):
        axes[r * ncols].set_ylabel("speedup over O3")
    header(fig, "Speedup over O3 by array size", subtitle(meta))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, outdir, "fig1_speedup_vs_size", formats)


def fig_speedup_largest(kernels, sizes, speedup, ok, meta, outdir, formats):
    n = sizes[-1]
    series = [c for c in ("offset", "greedy") if (kernels[0], c, n) in speedup]
    order = sorted(kernels, key=lambda k: speedup.get((k, "offset", n), 0))
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(kernels) + 2.0))
    bar_h = 0.34
    for i, c in enumerate(series):
        color, _ = SERIES[c]
        ys = [j + (0.5 - i) * (bar_h + 0.04) - 0.02 for j in range(len(order))]
        vals = [speedup.get((k, c, n), 0) for k in order]
        ax.barh(ys, vals, height=bar_h, color=color, label=LABELS[c], zorder=3)
        if c == "offset":  # Label the subject series only.
            for y, v, k in zip(ys, vals, order):
                txt = f"{v:.2f}×" + ("  (not executed)" if not ok.get((k, c, n), True) else "")
                ax.text(v + 0.03, y, txt, va="center", fontsize=8, color=INK)
    ax.axvline(1.0, color=INK_2, linewidth=1.0, zorder=4, label="O3 = 1×")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([KERNEL_TITLES.get(k, k) for k in order])
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.grid(True, axis="x", zorder=0)
    ax.set_xlim(0, max(speedup.get((k, c, n), 0) for k in order for c in series) * 1.25)
    ax.set_xlabel(f"speedup over O3 at {fmt_size(n)} elements per array")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=8.5,
              borderaxespad=0.3, handlelength=1.5)
    header(fig, f"Speedup at the memory-bound size ({fmt_size(n)} floats per array)",
           subtitle(meta))
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    save(fig, outdir, "fig2_speedup_largest", formats)


def fig_ablation(kernels, configs, sizes, speedup, ok, meta, outdir, formats, cache_n):
    cols = [c for c in configs if c != "O3"]
    panels = [cache_n, sizes[-1]]
    norm = TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)  # log2 speedup: 0.25× .. 4×
    fig, axes = plt.subplots(1, 2, figsize=(13, 0.42 * len(kernels) + 2.6), sharey=True)
    fig.subplots_adjust(left=0.17, right=0.9, top=0.84, bottom=0.2, wspace=0.04)
    for ax, n in zip(axes, panels):
        grid = [[math.log2(speedup[(k, c, n)]) if (k, c, n) in speedup else float("nan")
                 for c in cols] for k in kernels]
        im = ax.imshow(grid, cmap=DIVERGING, norm=norm, aspect="auto")
        for i, k in enumerate(kernels):
            for j, c in enumerate(cols):
                if (k, c, n) not in speedup:
                    continue
                v = speedup[(k, c, n)]
                rgb = DIVERGING(norm(math.log2(v)))[:3]
                lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
                txt = f"{v:.2f}" + ("!" if not ok.get((k, c, n), True) else "")
                ax.text(j, i, txt, ha="center", va="center", fontsize=7.5,
                        color="white" if lum < 0.45 else INK)
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([LABELS[c] for c in cols], rotation=35, ha="right")
        ax.set_yticks(range(len(kernels)))
        if ax is axes[0]:  # Both panels have the same rows.
            ax.set_yticklabels([KERNEL_TITLES.get(k, k) for k in kernels])
        ax.tick_params(length=0, labelleft=ax is axes[0])
        for s in ax.spines.values():
            s.set_visible(False)
        # 2px surface gaps between cells.
        ax.set_xticks([x - 0.5 for x in range(1, len(cols))], minor=True)
        ax.set_yticks([y - 0.5 for y in range(1, len(kernels))], minor=True)
        ax.grid(True, which="minor", color=SURFACE, linewidth=2)
        ax.tick_params(which="minor", length=0)
        kind = "cache-resident" if n == cache_n else "memory-bound"
        ax.set_title(f"{fmt_size(n)} floats per array ({kind})", loc="left",
                     fontweight="semibold", fontsize=10)
    cbar = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    ticks = [-2, -1, 0, 1, 2]
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([f"{2 ** t:g}×" for t in ticks])
    cbar.outline.set_visible(False)
    cbar.set_label("speedup over O3 (red: slower, blue: faster)", color=INK_2)
    header(fig, "Speedup of every configuration over O3",
           subtitle(meta) + ".  ! = optimized code not executed")
    save(fig, outdir, "fig3_ablation", formats)


def fig_geomean(kernels, configs, sizes, speedup, ok, meta, outdir, formats, cache_n):
    cols = [c for c in configs if c != "O3"]
    groups = [("cache-resident", [n for n in sizes if n <= cache_n], "#86b6ef"),
              ("memory-bound", [n for n in sizes if n > (1 << 20)], "#1c5cab")]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    bar_w = 0.38
    excluded = set()
    top = 0
    for g, (name, ns, color) in enumerate(groups):
        vals = []
        for c in cols:
            rs = []
            for k in kernels:
                for n in ns:
                    if (k, c, n) in speedup and ok.get((k, c, n), True):
                        rs.append(speedup[(k, c, n)])
                    elif (k, c, n) in speedup:
                        excluded.add(k)
            vals.append(statistics.geometric_mean(rs) if rs else float("nan"))
        top = max([top] + [v for v in vals if v == v])
        xs = [i + (g - 0.5) * (bar_w + 0.03) for i in range(len(cols))]
        sizes_txt = size_range(ns)
        ax.bar(xs, vals, width=bar_w, color=color, zorder=3,
               label=f"{name} ({sizes_txt} floats per array)")
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=7.5,
                    color=INK)
    ax.axhline(1.0, color=INK_2, linewidth=1.0, zorder=4, label="O3 = 1×")
    ax.set_ylim(0, top * 1.12)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([LABELS[c] for c in cols], rotation=25, ha="right")
    ax.tick_params(axis="x", length=0)
    ax.grid(True, axis="y", zorder=0)
    ax.set_ylabel("geometric-mean speedup over O3")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=8.5,
              borderaxespad=0.3, handlelength=1.5)
    note = subtitle(meta)
    if excluded:
        note += ".  Excluded (optimized code not executed): " + ", ".join(sorted(excluded))
    header(fig, "Geometric-mean speedup per configuration", note)
    fig.tight_layout(rect=(0, 0, 1, 0.85))
    save(fig, outdir, "fig4_geomean", formats)


def kernel_arrays(kernel):
    """Number of arrays a kernel touches: the pointer (or vector) parameters of
    its kernel_impl."""
    try:
        src = open(os.path.join(HERE, "kernels", kernel + ".cpp")).read()
    except OSError:
        return None
    m = re.search(r"KERNEL\s+kernel_impl\((.*?)\)", src, re.S)
    params = m.group(1) if m else ""
    return params.count("__restrict") + params.count("Vec &") or None


def cpu_caches(meta):
    """{"L1": bytes, ...} from meta.txt, or from sysfs for older results."""
    caches = {}
    for item in meta.get("caches", "").split():
        name, _, size = item.partition("=")
        caches[name] = int(size)
    if caches:
        return caches
    cpu = meta.get("cpu", "1").split()[0]
    base = f"/sys/devices/system/cpu/cpu{cpu}/cache"
    for idx in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = os.path.join(base, idx)
        if open(os.path.join(d, "type")).read().strip() == "Instruction":
            continue
        m = re.fullmatch(r"(\d+)([KM]?)", open(os.path.join(d, "size")).read().strip())
        if m:
            level = open(os.path.join(d, "level")).read().strip()
            caches["L" + level] = int(m.group(1)) * {"": 1, "K": 1 << 10, "M": 1 << 20}[m.group(2)]
    return caches


def cache_lines(ax, kernel, caches, sizes, label):
    """Vertical lines at the sizes where the kernel's arrays fill a cache level."""
    arrays = kernel_arrays(kernel)
    if not arrays:
        return
    for name, size in sorted(caches.items()):
        n = size / (4 * arrays)
        if not sizes[0] <= n <= sizes[-1]:
            continue
        ax.axvline(n, color=AXIS, linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)
        if label:
            ax.text(n * 1.06, 1.0, name, transform=ax.get_xaxis_transform(), ha="left",
                    va="top", fontsize=8, color=MUTED)


def end_labels(ax, ends):
    """Direct labels at the right end of the lines, pushed apart vertically."""
    lo, hi = ax.get_ylim()
    min_gap = 0.055 * (math.log2(hi) - math.log2(lo))  # About one text line, in log2 units.
    placed = []
    for c, y in sorted(ends, key=lambda e: e[1]):
        ly = math.log2(y)
        if placed and ly < placed[-1][1] + min_gap:
            ly = placed[-1][1] + min_gap
        placed.append((c, ly))
    x = ax.get_xlim()[1]
    for c, ly in placed:
        ax.annotate(LABELS[c], (x, 2 ** ly), xytext=(4, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=8, color=INK_2, annotation_clip=False)


def fig_kernel_sweep(results, outdir, formats):
    """One figure per kernel, three panels over the same size axis: O3's time
    per element, the speedup over O3 of the main configurations, and of the
    ablations of offset-aware fusion. Dashed lines mark the sizes at which the
    kernel's arrays fill L1, L2 and L3. Bands show the spread over the runs:
    gray = O3 against itself (the noise floor), blue = offset-aware fusion."""
    bench, times, ok, meta = load_runs(results)
    kernels = list(dict.fromkeys(r["kernel"] for r in bench))
    sizes = sorted({int(r["n"]) for r in bench})
    runs = int(meta.get("runs", 1) or 1)
    caches = cpu_caches(meta)
    sweep_dir = os.path.join(outdir, "sweep")
    os.makedirs(sweep_dir, exist_ok=True)

    def median_speedup(k, c, n):
        rs = run_speedups(times, k, c, n)
        return statistics.median(rs) if rs else None

    for k in kernels:
        fig, (ax_t, ax_m, ax_a) = plt.subplots(
            3, 1, figsize=(10, 10.5), sharex=True,
            gridspec_kw={"height_ratios": (1, 2.3, 2.3), "hspace": 0.22})
        fig.subplots_adjust(left=0.09, right=0.8, top=0.88, bottom=0.17)

        # O3 time per element: shows where the cache levels start to matter.
        xs = [n for n in sizes if (k, "O3", n) in times]
        ys = [statistics.median(times[(k, "O3", n)].values()) / n for n in xs]
        ax_t.plot(xs, ys, color=INK_2, linewidth=1.6, zorder=3)
        ax_t.set_ylim(0, max(ys) * 1.2)
        ax_t.set_ylabel("ns per element")
        ax_t.grid(True, axis="y")
        cache_lines(ax_t, k, caches, sizes, label=True)
        ax_t.set_title("O3 time per element", loc="left", fontweight="semibold")

        vals = []
        labeled = []  # (axis, line ends): direct labels, placed once the limits are final.
        for ax, series, title, direct in (
                (ax_m, SWEEP_MAIN, "Speedup over O3: Polly configurations", True),
                (ax_a, SWEEP_ABLATION, "Speedup over O3: ablations of offset-aware fusion",
                 False)):
            ax.grid(True, axis="y")
            cache_lines(ax, k, caches, sizes, label=False)
            if runs > 1:
                # O3 against its own median: anything inside is run-to-run noise.
                lo_hi = []
                for n in xs:
                    t = list(times[(k, "O3", n)].values())
                    med = statistics.median(t)
                    lo_hi.append((min(med / v for v in t), max(med / v for v in t)))
                ax.fill_between(xs, [a for a, _ in lo_hi], [b for _, b in lo_hi],
                                color=GRID, linewidth=0, zorder=1)
                vals += [v for pair in lo_hi for v in pair]
                band = [(n, run_speedups(times, k, "offset", n)) for n in sizes]
                band = [(n, rs) for n, rs in band if rs]
                if band:
                    vals += [v for _, rs in band for v in (min(rs), max(rs))]
                    ax.fill_between([n for n, _ in band], [min(rs) for _, rs in band],
                                    [max(rs) for _, rs in band], color=SERIES["offset"][0],
                                    alpha=0.16, linewidth=0, zorder=2)
            ax.axhline(1.0, color=INK_2, linewidth=1.0, zorder=2)
            ends = []
            for c in reversed(series):  # The subject series (offset) on top.
                pts = [(n, median_speedup(k, c, n)) for n in sizes]
                pts = [(n, v) for n, v in pts if v]
                if not pts:
                    continue
                ax.plot([n for n, _ in pts], [v for _, v in pts], color=SERIES[c][0],
                        linewidth=2.2 if c == "offset" else 1.5,
                        zorder=4 if c == "offset" else 3,
                        solid_capstyle="round", solid_joinstyle="round")
                vals += [v for _, v in pts]
                ends.append((c, pts[-1][1]))
            if any(not ok.get((k, c, n), True) for c in series for n in sizes):
                ax.text(0.02, 0.04, "optimized code not executed", transform=ax.transAxes,
                        color=MUTED, fontsize=8)
            ax.set_title(title, loc="left", fontweight="semibold")
            ax.set_ylabel("speedup over O3")
            if direct:
                labeled.append((ax, ends))
        size_ticks(ax_a, sizes)
        ax_a.set_xlabel("elements per array (4 B each)")
        lo = max(1 / 32, 2 ** math.floor(math.log2(min(vals + [0.5]))))
        hi = min(8, 2 ** math.ceil(math.log2(max(vals + [2.0]))))
        for ax in (ax_m, ax_a):
            log_speedup_axis(ax, lo, hi)
        for ax, ends in labeled:
            end_labels(ax, ends)

        # One legend for both speedup panels; configurations keep their color.
        configs = list(dict.fromkeys(SWEEP_MAIN + SWEEP_ABLATION))
        handles = [Line2D([], [], color=SERIES[c][0], linewidth=2, label=LABELS[c])
                   for c in configs]
        handles.append(Line2D([], [], color=INK_2, linewidth=1.0, label="O3 = 1×"))
        if runs > 1:
            handles.append(Patch(color=GRID, label="O3 against itself (noise)"))
            handles.append(Patch(color=SERIES["offset"][0], alpha=0.16,
                                 label="offset: spread over runs"))
        ax_a.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.14), ncol=4,
                    fontsize=8, handlelength=1.6, columnspacing=1.4)

        arrays = kernel_arrays(k)
        note = subtitle(meta)
        if arrays:
            note += f".  Dashed: the {arrays} arrays (n × 4 B each) fill L1, L2, L3"
        header(fig, f"{KERNEL_TITLES.get(k, k)}: speedup over O3 by array size", note)
        save(fig, sweep_dir, k, formats)


def write_table(kernels, configs, sizes, speedup, ok, outdir):
    with open(os.path.join(outdir, "speedup.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kernel", "config", "n", "speedup_over_O3", "optimized_code_executed"])
        for k in kernels:
            for c in configs:
                for n in sizes:
                    if (k, c, n) in speedup:
                        w.writerow([k, c, n, f"{speedup[(k, c, n)]:.4f}",
                                    int(ok.get((k, c, n), True))])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="?", help="results directory (default: newest)")
    ap.add_argument("--cache-size", type=int, default=16384,
                    help="cache-resident size for fig3/fig4 (default 16384)")
    ap.add_argument("--format", default="png,svg")
    args = ap.parse_args()
    results = args.results
    if not results:
        base = os.path.join(HERE, "results")
        dirs = sorted(d for d in os.listdir(base)
                      if os.path.exists(os.path.join(base, d, "bench.csv")))
        if not dirs:
            sys.exit("no results with bench.csv found")
        results = os.path.join(base, dirs[-1])
    if not os.path.exists(os.path.join(results, "bench.csv")):
        sys.exit(f"{results}/bench.csv not found (was run.py started with --no-bench?)")
    kernels, configs, sizes, speedup, ok, meta = load(results)
    if args.cache_size not in sizes:
        sys.exit(f"--cache-size {args.cache_size} is not a measured size: {sizes}")
    outdir = os.path.join(results, "figures")
    os.makedirs(outdir, exist_ok=True)
    formats = args.format.split(",")
    style()
    fig_speedup_vs_size(kernels, sizes, speedup, ok, meta, outdir, formats)
    fig_speedup_largest(kernels, sizes, speedup, ok, meta, outdir, formats)
    fig_ablation(kernels, configs, sizes, speedup, ok, meta, outdir, formats, args.cache_size)
    fig_geomean(kernels, configs, sizes, speedup, ok, meta, outdir, formats, args.cache_size)
    fig_kernel_sweep(results, outdir, formats)
    write_table(kernels, configs, sizes, speedup, ok, outdir)
    print(f"figures written to {outdir}")


if __name__ == "__main__":
    main()
