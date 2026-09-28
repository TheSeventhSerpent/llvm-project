// Four transforms with offsets 0, +1, output +1 (input 0), +2.
// EXPECT offset: shifted>=1 isolated>=1
#include "kernel.h"
#include <algorithm>

KERNEL kernel_impl(float *__restrict a, float *__restrict b,
                   float *__restrict c, float *__restrict d, long n) {
  if (n < 4)
    return;
  std::transform(a, a + n, b, [](float x) { return x * 0.5f + 1.0f; });
  std::transform(b + 1, b + n, c + 1, [](float x) { return x + 1.0f; });
  std::transform(c, c + n - 1, d + 1, [](float x) { return x * 0.25f; });
  std::transform(d + 2, d + n, a + 2, [](float x) { return x - 2.0f; });
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl(a.data(), b.data(), c.data(), d.data(), (long)a.size());
}
