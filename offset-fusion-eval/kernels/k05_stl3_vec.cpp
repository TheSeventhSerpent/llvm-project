// The same chain on std::vector::data(), without __restrict. Polly has to
// check at run time that the vectors do not alias.
//
// Known limitation: Polly cannot model the first loop ("Failed to derive an
// affine function from the loop bounds"; its trip count is derived from the
// vector's end and begin pointers), so only the last two loops form a SCoP.
// They are fused, without a shift, but the SCoP is then not code-generated
// ("Invariant load assumption: false"), so no optimized code is executed.
// EXPECT offset: plain>=1
// EXPECT *: nopolly
#include "kernel.h"
#include <algorithm>

KERNEL kernel_impl(Vec &va, Vec &vb, Vec &vc) {
  long n = (long)va.size();
  if (n < 2)
    return;
  float *a = va.data(), *b = vb.data(), *c = vc.data();
  std::transform(a, a + n, b, [](float x) { return x * 0.5f + 1.0f; });
  std::transform(b + 1, b + n, c + 1, [](float x) { return x + 1.0f; });
  std::transform(c, c + n - 1, a, [](float x) { return x - 1.0f; });
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) { kernel_impl(a, b, c); }
