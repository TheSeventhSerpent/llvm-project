// Different algorithms: iota, transform, replace_if, for_each, fill.
// EXPECT offset: fused>=1
#include "kernel.h"
#include <algorithm>
#include <numeric>

KERNEL kernel_impl(float *__restrict a, float *__restrict b,
                   float *__restrict c, float *__restrict d, long n) {
  if (n < 4)
    return;
  std::iota(a, a + n, 0.0f);
  std::transform(a + 1, a + n, b + 1, [](float x) { return x * 0.5f; });
  std::replace_if(b + 1, b + n, [](float x) { return x > 100.0f; }, 100.0f);
  std::for_each(c + 2, c + n, [](float &x) { x = x * 0.5f + 1.0f; });
  std::fill(d, d + n - 1, 3.0f);
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl(a.data(), b.data(), c.data(), d.data(), (long)a.size());
}
