// Six transforms with offsets 0, +1, +2, 0, +1, 0.
// EXPECT offset: shifted>=1 isolated>=1
#include "kernel.h"
#include <algorithm>

KERNEL kernel_impl(float *__restrict a, float *__restrict b,
                   float *__restrict c, float *__restrict d, long n) {
  if (n < 4)
    return;
  auto F = [](float x) { return x * 0.5f + 1.0f; };
  std::transform(a, a + n, b, F);
  std::transform(b + 1, b + n, c + 1, F);
  std::transform(c + 2, c + n, d + 2, F);
  std::transform(d, d + n, b, F);
  std::transform(b + 1, b + n, c + 1, F);
  std::transform(c, c + n, d, F);
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl(a.data(), b.data(), c.data(), d.data(), (long)a.size());
}
