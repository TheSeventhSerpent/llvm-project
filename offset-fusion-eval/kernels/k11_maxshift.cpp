// The second loop starts at 10, more than the default maximal shift of 4.
// EXPECT offset: shifted==0
#include "kernel.h"

KERNEL kernel_impl(long n, float *__restrict A, float *__restrict B,
                   float *__restrict C) {
  for (long i = 0; i < n; i++)  B[i] = A[i] * 0.5f + 1.0f;
  for (long i = 10; i < n; i++) C[i] = B[i] + 1.0f;
}

void run(Vec &a, Vec &b, Vec &c, Vec &d) {
  kernel_impl((long)a.size(), a.data(), b.data(), c.data());
}
