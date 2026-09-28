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

Speedup = median time of O3 / median time of the configuration; > 1 is
faster than O3. Configurations whose optimized code is not executed (the
kernel falls back to the original code) are marked, and left out of the
geometric means.
"""
import argparse
import csv
import math
import os
import statistics
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

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
}
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


def load(results):
    bench = list(csv.DictReader(open(os.path.join(results, "bench.csv"))))
    meta = {}
    for line in open(os.path.join(results, "meta.txt")):
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    kernels = list(dict.fromkeys(r["kernel"] for r in bench))
    configs = list(dict.fromkeys(r["config"] for r in bench))
    sizes = sorted({int(r["n"]) for r in bench})
    t = {(r["kernel"], r["config"], int(r["n"])): int(r["median_ns"]) for r in bench}
    ok = {(r["kernel"], r["config"], int(r["n"])): r["polly_path"] != "0" for r in bench}
    speedup = {}
    for (k, c, n), v in t.items():
        base = t.get((k, "O3", n))
        if base and v:
            speedup[(k, c, n)] = base / v
    return kernels, configs, sizes, speedup, ok, meta


def subtitle(meta):
    cpu = meta.get("cpu", "?")
    num, _, model = cpu.partition(" (")
    model = model.rstrip(")").replace("12th Gen Intel(R) Core(TM) ", "")
    s = f"{model or '?'}, pinned to CPU {num}, governor {meta.get('governor', '?')}, " \
        f"median of {meta.get('reps', '?')} runs, commit {meta.get('git', '?')}"
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


def log_speedup_axis(ax, lo, hi):
    ax.set_yscale("log", base=2)
    ticks = [t for t in (0.125, 0.25, 0.5, 1, 2, 4, 8) if lo <= t <= hi]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}×" for t in ticks])
    ax.minorticks_off()
    ax.set_ylim(lo, hi)


def fig_speedup_vs_size(kernels, sizes, speedup, ok, meta, outdir, formats):
    series = [c for c in SERIES if any((k, c, sizes[0]) in speedup for k in kernels)]
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
            ax.plot(xs, ys, color=color, linewidth=2, marker=marker, markersize=5,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3,
                    solid_capstyle="round", solid_joinstyle="round")
        title = KERNEL_TITLES.get(k, k)
        ax.set_title(title, loc="left", fontweight="semibold")
        if any(not ok.get((k, c, n), True) for c in series for n in sizes):
            ax.text(0.02, 0.04, "optimized code not executed", transform=ax.transAxes,
                    color=MUTED, fontsize=8)
        ax.set_xscale("log", base=2)
        ax.set_xticks(sizes)
        ax.set_xticklabels([fmt_size(n) for n in sizes])
        ax.minorticks_off()
        log_speedup_axis(ax, lo, hi)
    for ax in axes[len(kernels):]:
        ax.axis("off")
    # Legend in the first free panel.
    leg_ax = axes[len(kernels)]
    handles = [Line2D([], [], color=SERIES[c][0], marker=SERIES[c][1], linewidth=2,
                      markersize=6, markeredgecolor=SURFACE, label=LABELS[c]) for c in series]
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
        sizes_txt = ", ".join(fmt_size(n) for n in ns)
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
    write_table(kernels, configs, sizes, speedup, ok, outdir)
    print(f"figures written to {outdir}")


if __name__ == "__main__":
    main()
