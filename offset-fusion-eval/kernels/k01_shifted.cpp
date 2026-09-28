// The diploma example: loops over [0, n), [1, n) and [0, n - 1).
// EXPECT offset: shifted>=1 isolated>=1
#include "kernel.h"

KERNEL kernel_impl(long n, float *__restrict A, float *__restrict B,
                   float *__restrict C, float *__restrict D) {
  for (long i = 0; i < n; i++)     B[i] = A[i] * 0.5f + 1.0f;
  for (long i = 1; i < n; i++)     C[i] = B[i] + 1.0f;
  for (long i = 0; i < n - 1; i++) D[i] = C[i] - B[i];
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl((long)a.size(), a.data(), b.data(), c.data(), d.data());
}
