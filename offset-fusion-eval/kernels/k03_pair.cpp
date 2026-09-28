// Two loops that can be fused without a shift, but are misaligned by one
// element. -polly-offset-fusion-prefer-aligned aligns them.
// EXPECT offset: plain>=1
// EXPECT aligned: shifted>=1 isolated>=1
#include "kernel.h"

KERNEL kernel_impl(long n, float *__restrict B, float *__restrict C,
                   float *__restrict D) {
  for (long i = 1; i < n; i++)     C[i] = B[i] + 1.0f;
  for (long i = 0; i < n - 1; i++) D[i] = C[i] * 0.5f;
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl((long)a.size(), b.data(), c.data(), d.data());
}
