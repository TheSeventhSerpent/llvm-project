// Three loops over the same range: plain fusion.
// EXPECT offset: plain>=2
#include "kernel.h"

KERNEL kernel_impl(long n, float *__restrict A, float *__restrict B,
                   float *__restrict C, float *__restrict D) {
  for (long i = 0; i < n; i++) B[i] = A[i] * 0.5f + 1.0f;
  for (long i = 0; i < n; i++) C[i] = B[i] + 1.0f;
  for (long i = 0; i < n; i++) D[i] = C[i] - B[i];
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl((long)a.size(), a.data(), b.data(), c.data(), d.data());
}
