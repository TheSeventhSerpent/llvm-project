//===- OffsetFusion.h - Helpers for offset-aware loop fusion ----*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// Options and pure isl helpers for offset-aware loop fusion: fusing loops whose
// iteration domains are shifted against each other by a constant, e.g. loops
// over [0, N), [1, N) and [0, N - 1) that process the same logical range of
// elements.
//
// The physical iterator of a statement starts at 0. The logical offset δ of a
// statement relates it to the element index it processes:
//   logical index = physical iterator + δ
//
//===----------------------------------------------------------------------===//

#ifndef POLLY_SUPPORT_OFFSETFUSION_H
#define POLLY_SUPPORT_OFFSETFUSION_H

#include "isl/isl-noexceptions.h"
#include <cstdint>
#include <optional>

namespace polly {

/// Master switch: -polly-force-offset-fusion. The options are defined in
/// ScheduleOptimizer.cpp.
extern bool PollyForceOffsetFusion;

/// Ablation switches. Only read if PollyForceOffsetFusion is set.
/// Add offset-based proximity relations to the scheduler input.
extern bool PollyOffsetFusionProximity;
/// Allow greedy fusion with a constant schedule shift.
extern bool PollyOffsetFusionShift;
/// Isolate the common interior of offset-fused loops.
extern bool PollyOffsetFusionIsolate;
/// Maximal absolute schedule shift for a fusion.
extern unsigned PollyOffsetFusionMaxShift;
/// Maximal number of statements for the pairwise proximity computation.
extern unsigned PollyOffsetFusionMaxStmts;

/// Name of the mark inserted above bands produced by offset-aware fusion.
constexpr const char *OffsetFusionMarkName = "Offset-aware fusion";

/// Compute the logical offset δ implied by a single array access.
///
/// For a one-dimensional statement with the affine subscript s * k + b, where
/// s > 0 and b are integer constants and s divides b, return δ = b / s. That
/// is, the statement instance k accesses the element that instance k + δ of
/// an unshifted traversal with the same stride would access.
///
/// @param Domain The statement's iteration domain.
/// @param Access The access relation { Stmt[k] -> Array[i] }.
///
/// @return δ, or std::nullopt if the access has no constant logical offset
///         (multi-dimensional, non-affine, parametric, non-positive stride,
///         ...).
std::optional<int64_t> getOffsetFromAccess(isl::set Domain, isl::map Access);

/// Return { Stmt[k] -> Stmt[k + Delta] } for the one-dimensional statement
/// space @p DomainSpace.
isl::map physicalToLogical(isl::space DomainSpace, int64_t Delta);

/// Shift a one-dimensional domain by @p Delta: { Stmt[k + Delta] : k in
/// Domain }.
isl::set shiftDomain(isl::set Domain, int64_t Delta);

/// Check whether two logical (i.e. shifted) domains can be aligned by a
/// constant shift.
///
/// Both domains must be one-dimensional, their lower and upper bounds must
/// differ by constants that do not depend on the parameters, and the domains
/// must overlap. Tuple ids are ignored.
bool areShiftCompatible(isl::set LogA, isl::set LogB, isl::set Context);

/// Build the offset proximity relation between two statements.
///
/// Relates the instances of @p SrcDomain and @p DstDomain that process the same
/// logical index, expressed on the physical instances:
///   { Src[k] -> Dst[k + SrcOffset - DstOffset] }
/// restricted to both domains, i.e. to the shared logical range.
///
/// @return The relation, or a null map if the logical domains are not
///         shift-compatible (see areShiftCompatible).
isl::map getOffsetProximity(isl::set SrcDomain, int64_t SrcOffset,
                            isl::set DstDomain, int64_t DstOffset,
                            isl::set Context);

/// Compute the smallest shift Δ >= 0 such that scheduling the RHS instances at
/// @p RHSOuter + Δ does not execute any dependence target before its source
/// scheduled at @p LHSOuter.
///
/// @param LHSOuter The outermost schedule dimension of the LHS statements.
/// @param RHSOuter The outermost schedule dimension of the RHS statements.
/// @param Deps     Dependences to respect.
///
/// @return Δ, or std::nullopt if the required shift is unbounded.
std::optional<int64_t> getMinimalLegalShift(isl::union_pw_aff LHSOuter,
                                            isl::union_pw_aff RHSOuter,
                                            isl::union_map Deps);

} // namespace polly

#endif // POLLY_SUPPORT_OFFSETFUSION_H
