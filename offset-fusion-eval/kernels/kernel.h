// Common interface of the evaluation kernels.
//
// Every kernel file defines `run`, which the driver calls. Pointer kernels
// implement the loops in a separate noinline function with __restrict
// parameters, called from `run` with the vectors' data().
#ifndef OFFSET_FUSION_EVAL_KERNEL_H
#define OFFSET_FUSION_EVAL_KERNEL_H

#include <vector>

using Vec = std::vector<float>;

// All four vectors have the same size n.
void run(Vec &a, Vec &b, Vec &c, Vec &d);

#define KERNEL extern "C" __attribute__((noinline)) void

#endif
