// Mixed unary and binary transforms. The binary transform reads two arrays at
// different offsets, so its statement has no single logical offset.
// EXPECT offset: polly
#include "kernel.h"
#include <algorithm>
#include <functional>

KERNEL kernel_impl(float *__restrict a, float *__restrict b,
                   float *__restrict c, float *__restrict d, long n) {
  if (n < 3)
    return;
  std::transform(a, a + n, b, [](float x) { return x * 0.5f + 1.0f; });
  std::transform(a + 1, a + n, b, c + 1, std::plus<float>());
  std::transform(c + 1, c + n, d + 1, [](float x) { return x - 1.0f; });
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl(a.data(), b.data(), c.data(), d.data(), (long)a.size());
}
