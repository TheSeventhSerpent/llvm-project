// Driver for the offset-fusion evaluation. Compiled once with plain -O3 and
// linked with one kernel object, which is compiled with the configuration under
// test.
//
//   driver check          Run the kernel for many sizes and print a checksum
//                         of all arrays per size ("n=<n> <hash>").
//   driver bench N REPS   Run the kernel REPS times on arrays of size N and
//                         print "median_ns=<t> min_ns=<t>". The inputs are
//                         re-initialized (untimed) before every run. With
//                         REPS = 0, the kernel runs once and nothing is
//                         printed.
#include "kernels/kernel.h"
#include <algorithm>
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static void init(Vec &a, Vec &b, Vec &c, Vec &d) {
  for (size_t i = 0; i < a.size(); i++) {
    a[i] = (float)(i * 37 % 101) * 0.25f - 3.0f;
    b[i] = (float)(i * 11 % 23) * 0.5f;
    c[i] = (float)(i % 7) - 1.0f;
    d[i] = -2.0f;
  }
}

// FNV-1a over the bytes of all arrays: results must be bit-identical.
static uint64_t hash(const Vec &a, const Vec &b, const Vec &c, const Vec &d) {
  uint64_t H = 1469598103934665603ull;
  for (const Vec *V : {&a, &b, &c, &d}) {
    const unsigned char *P = (const unsigned char *)V->data();
    for (size_t i = 0; i < V->size() * sizeof(float); i++)
      H = (H ^ P[i]) * 1099511628211ull;
  }
  return H;
}

static int check() {
  const long Sizes[] = {0,  1,  2,  3,  4,  5,   6,   7,    8,   9,
                        10, 11, 12, 13, 17, 31, 64, 100, 1000, 4099};
  for (long N : Sizes) {
    Vec a(N), b(N), c(N), d(N);
    init(a, b, c, d);
    run(a, b, c, d);
    std::printf("n=%ld %016" PRIx64 "\n", N, hash(a, b, c, d));
    std::fflush(stdout);
  }
  return 0;
}

static int bench(long N, int Reps) {
  Vec a(N), b(N), c(N), d(N);
  std::vector<double> Times;
  for (int R = -1; R < Reps; R++) { // One warm-up run.
    init(a, b, c, d);
    auto Start = std::chrono::steady_clock::now();
    run(a, b, c, d);
    auto End = std::chrono::steady_clock::now();
    if (R >= 0)
      Times.push_back(std::chrono::duration<double, std::nano>(End - Start).count());
  }
  if (Times.empty()) // REPS = 0: only the (untimed) warm-up run.
    return 0;
  std::sort(Times.begin(), Times.end());
  std::printf("median_ns=%.0f min_ns=%.0f\n", Times[Times.size() / 2], Times[0]);
  return 0;
}

int main(int argc, char **argv) {
  if (argc >= 2 && !std::strcmp(argv[1], "check"))
    return check();
  if (argc >= 4 && !std::strcmp(argv[1], "bench"))
    return bench(std::atol(argv[2]), std::atoi(argv[3]));
  std::fprintf(stderr, "usage: %s check | bench N REPS\n", argv[0]);
  return 2;
}
