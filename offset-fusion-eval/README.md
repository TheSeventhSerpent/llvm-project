# Offset-aware fusion: evaluation harness

Scripts for evaluating `-polly-force-offset-fusion`, following section 9 of
the implementation plan. These scripts are not part of Polly and not meant for
upstream.

## Usage

```sh
# Correctness and transformation checks only (about a minute):
./run.py --no-bench

# Full run: all kernels, all configurations, default sizes:
./run.py

# Subset, with cache-miss counters:
./run.py --kernels k01_shifted,k04_stl3 --configs offset,noiso --perf
```

It uses `build/bin/clang++` from this repository (`--clang` to override).
Results go to `results/<timestamp>/` (`--out` to override):

| File | Content |
|---|---|
| `summary.md` | problems, transformation statistics per kernel and configuration, speedup tables |
| `correctness.csv` | statistics, Polly code in the IR, sizes at which the optimized code ran, bit-exact match with O3 |
| `bench.csv` | median and minimum time per kernel, configuration and size |
| `meta.txt` | compiler, git revision, CPU and governor |
| `build/` | objects, IR and build logs per kernel and configuration |

`run.py` exits with status 1 if any check fails.

## Figures

`plot.py` turns a run with benchmarks into figures (PNG and SVG) plus a table
view (`speedup.csv`), written to `<results>/figures/`. It needs matplotlib,
installed in a local venv:

```sh
python3 -m venv .venv && .venv/bin/pip install matplotlib
.venv/bin/python plot.py                 # newest run in results/
.venv/bin/python plot.py results/<run> --cache-size 16384 --format png,svg,pdf
```

| Figure | Content |
|---|---|
| `fig1_speedup_vs_size` | speedup over O3 by array size, one panel per kernel (offset, greedy, aligned) |
| `fig2_speedup_largest` | speedup per kernel at the largest size, offset vs greedy |
| `fig3_ablation` | every configuration × kernel, cache-resident vs memory-bound size |
| `fig4_geomean` | geometric-mean speedup per configuration, cache-resident vs memory-bound |

Runs without the performance governor are labeled "Preliminary" in every
figure. Measurements whose optimized code was not executed are marked, and are
left out of the geometric means.

## What is checked

For every kernel and configuration:

1. **Correctness.** `driver check` runs the kernel for 20 sizes (0–13, 17, 31,
   64, 100, 1000, 4099) and hashes all arrays. The hashes must be bit-identical
   to plain `-O3`. The small sizes cover the prologue, the epilogue and the
   fallback paths of the isolated loops.
2. **The optimized code is really executed** (plan section 9.3). Polly falls
   back to the original code silently, e.g. when its run-time check (RTC) fails.
   - The `-O3` IR must contain blocks of Polly's optimized code version.
   - A build with `-polly-codegen-emit-rtc-print` must report a successful RTC
     for every checked size >= 17, and for every benchmark size.
3. **Expectations.** Each kernel states what offset fusion must do, e.g.
   `// EXPECT offset: shifted>=1 isolated>=1`. Tokens are `<stat><op><int>`
   (stat: `offsets`, `proximity`, `plain`, `shifted`, `fused` = plain + shifted,
   `isolated`; op: `>=`, `==`, `<=`), `polly` and `nopolly`. The configuration
   may be `*` for all Polly configurations.

In the summary, `!` marks configurations whose optimized code is not executed,
and `X` marks wrong results.

## Configurations

All Polly configurations use `-O3 -mllvm -polly -mllvm -polly-process-unprofitable`.

| Name | Additional options |
|---|---|
| `O3` | none (no Polly); the reference |
| `polly` | |
| `greedy` | `-polly-loopfusion-greedy` |
| `offset` | `-polly-force-offset-fusion` |
| `noprox` | offset + `-polly-offset-fusion-proximity=0` |
| `noshift` | offset + `-polly-offset-fusion-shift=0` |
| `noiso` | offset + `-polly-offset-fusion-isolate=0` |
| `aligned` | offset + `-polly-offset-fusion-prefer-aligned` |
| `unserialize` | offset + `-polly-offset-fusion-unserialize` |

## Kernels

`kernels/*.cpp`, each in its own translation unit. `driver.cpp` is compiled once
with plain `-O3`, so statistics and run-time checks come only from the kernel.

| Kernel | Content |
|---|---|
| `k01_shifted` | the diploma example: loops over [0, n), [1, n), [0, n - 1) |
| `k02_three` | three loops over the same range |
| `k03_pair` | two loops that are fusable without a shift, but misaligned |
| `k04_stl3` | `std::transform` chain over pointers, offsets 0, +1, 0 |
| `k05_stl3_vec` | the same on `std::vector::data()`; not optimized by Polly (see the file) |
| `k06_chain2_off2` | two transforms, offset +2 |
| `k07_chain4_mixed` | four transforms, mixed offsets |
| `k08_chain6` | six transforms |
| `k09_algos` | `iota`, `transform`, `replace_if`, `for_each`, `fill` |
| `k10_binary` | unary and binary transforms mixed |
| `k11_maxshift` | offset 10, above the default maximal shift of 4: not fused |

## Measurement notes

- Benchmarks are pinned (`taskset`) to the CPU with the highest maximal
  frequency, i.e. a P-core on hybrid CPUs (`--cpu` to override).
- Set the performance governor for stable timings:
  `sudo cpupower frequency-set -g performance`. The governor is recorded in
  `meta.txt`, and `run.py` warns if it is not `performance`.
- `--perf` needs `sudo sysctl kernel.perf_event_paranoid=1`. The counters cover
  all runs of a benchmark, including the untimed input initialization.
- Each benchmark is the median of `--reps` runs (default 11) after one warm-up
  run. Inputs are re-initialized before every run, outside the timed region.
