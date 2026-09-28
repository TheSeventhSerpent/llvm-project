//===- OffsetFusion.cpp - Helpers for offset-aware loop fusion ------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
//
// Pure isl helpers for offset-aware loop fusion. The options are defined in
// ScheduleOptimizer.cpp, which is always linked.
//
//===----------------------------------------------------------------------===//

#include "polly/Support/OffsetFusion.h"
#include "polly/Support/ISLTools.h"
#include "isl/aff.h"
#include "isl/ilp.h"
#include "isl/set.h"
#include <algorithm>
#include <limits>

using namespace polly;

/// Convert an integer isl::val to int64_t, if it fits into 32 bits. Offsets and
/// shifts are small in practice; the bound keeps later arithmetic on them from
/// overflowing.
static std::optional<int64_t> getSmallInt(isl::val V) {
  if (V.is_null() || !V.is_int())
    return std::nullopt;
  isl::ctx Ctx = V.ctx();
  isl::val Max(Ctx, std::numeric_limits<int32_t>::max());
  if (V.abs().gt(Max))
    return std::nullopt;
  return V.get_num_si();
}

std::optional<int64_t> polly::getOffsetFromAccess(isl::set Domain,
                                                  isl::map Access) {
  if (Domain.is_null() || Access.is_null())
    return std::nullopt;

  // One-dimensional statement and one-dimensional array subscript. Multi-
  // dimensional (e.g. delinearized) arrays are not supported.
  if (unsignedFromIslSize(Domain.tuple_dim()) != 1 ||
      unsignedFromIslSize(Access.domain_tuple_dim()) != 1 ||
      unsignedFromIslSize(Access.range_tuple_dim()) != 1)
    return std::nullopt;

  isl::map A = Access.intersect_domain(Domain);
  if (A.is_empty() || !A.is_single_valued())
    return std::nullopt;

  // The subscript must be a single affine piece.
  isl::pw_multi_aff PMA = A.as_pw_multi_aff();
  if (PMA.is_null() || unsignedFromIslSize(PMA.n_piece()) != 1)
    return std::nullopt;
  isl::aff Aff;
  PMA.foreach_piece([&](isl::set, isl::multi_aff MA) -> isl::stat {
    Aff = MA.at(0);
    return isl::stat::ok();
  });
  if (Aff.is_null() || unsignedFromIslSize(Aff.dim(isl::dim::div)) != 0)
    return std::nullopt;

  auto Coeff = [&](isl_dim_type Type, int Pos) {
    return isl::manage(isl_aff_get_coefficient_val(Aff.get(), Type, Pos));
  };

  // The offset must not depend on parameters.
  for (unsigned P = 0; P < unsignedFromIslSize(Aff.dim(isl::dim::param)); ++P)
    if (!Coeff(isl_dim_param, P).is_zero())
      return std::nullopt;

  // The subscript is S * k + B. Physical iterators start at 0, so B is the
  // subscript of the first iteration and S the stride between iterations.
  // Only forward traversals are supported.
  isl::val S = Coeff(isl_dim_in, 0);
  isl::val B = Aff.constant_val();
  if (S.is_null() || B.is_null() || !S.is_int() || !B.is_int() || !S.is_pos())
    return std::nullopt;
  if (!B.is_divisible_by(S))
    return std::nullopt;
  return getSmallInt(B.div(S));
}

isl::map polly::physicalToLogical(isl::space DomainSpace, int64_t Delta) {
  // { Stmt[k] -> Stmt[k] }
  isl::multi_aff Id = isl::multi_aff::identity_on_domain(DomainSpace);
  // k + Delta
  isl::aff Shifted =
      Id.at(0).add_constant(isl::val(DomainSpace.ctx(), (long)Delta));
  return Id.set_at(0, Shifted).as_map();
}

isl::set polly::shiftDomain(isl::set Domain, int64_t Delta) {
  return Domain.apply(physicalToLogical(Domain.get_space(), Delta));
}

/// Check whether @p Diff has the same constant value wherever it is defined,
/// independent of the parameters.
static bool isConstantDifference(isl::pw_aff Diff) {
  if (Diff.is_null())
    return false;
  isl::val Min = isl::manage(isl_pw_aff_min_val(Diff.copy()));
  isl::val Max = isl::manage(isl_pw_aff_max_val(Diff.copy()));
  if (Min.is_null() || Max.is_null() || !Min.is_int() || !Max.is_int())
    return false;
  return Min.eq(Max);
}

bool polly::areShiftCompatible(isl::set LogA, isl::set LogB, isl::set Context) {
  if (LogA.is_null() || LogB.is_null() || Context.is_null())
    return false;

  // (1) Same dimensionality; only one-dimensional domains are supported.
  if (unsignedFromIslSize(LogA.tuple_dim()) != 1 ||
      unsignedFromIslSize(LogB.tuple_dim()) != 1)
    return false;

  LogA = LogA.intersect_params(Context);
  LogB = LogB.intersect_params(Context);

  // Only compare the bounds for parameter values where both domains are
  // non-empty. Otherwise, dim_min/dim_max have additional pieces for small
  // parameter values.
  isl::set NonEmpty = LogA.params().intersect(LogB.params());
  if (NonEmpty.is_empty())
    return false;

  // (2) Lower and upper bounds differ by constants. dim_min/dim_max are an
  // error for unbounded dimensions, which Polly turns into an abort.
  for (isl::set Log : {LogA, LogB})
    if (isl_set_dim_has_lower_bound(Log.get(), isl_dim_set, 0) !=
            isl_bool_true ||
        isl_set_dim_has_upper_bound(Log.get(), isl_dim_set, 0) != isl_bool_true)
      return false;
  isl::pw_aff DiffLower = LogB.dim_min(0).sub(LogA.dim_min(0));
  isl::pw_aff DiffUpper = LogB.dim_max(0).sub(LogA.dim_max(0));
  if (!isConstantDifference(DiffLower.intersect_params(NonEmpty)) ||
      !isConstantDifference(DiffUpper.intersect_params(NonEmpty)))
    return false;

  // (3) The logical ranges overlap.
  return !LogA.reset_tuple_id().intersect(LogB.reset_tuple_id()).is_empty();
}

isl::map polly::getOffsetProximity(isl::set SrcDomain, int64_t SrcOffset,
                                   isl::set DstDomain, int64_t DstOffset,
                                   isl::set Context) {
  if (SrcDomain.is_null() || DstDomain.is_null() || Context.is_null())
    return {};
  if (!areShiftCompatible(shiftDomain(SrcDomain, SrcOffset),
                          shiftDomain(DstDomain, DstOffset), Context))
    return {};

  // Src[k] processes logical index k + SrcOffset, which Dst processes in
  // iteration k + SrcOffset - DstOffset. Restricting the relation to both
  // domains restricts it to the logical indices processed by both.
  isl::map Rel = physicalToLogical(SrcDomain.get_space(), SrcOffset - DstOffset)
                     .set_range_tuple(DstDomain.get_tuple_id());
  return Rel.intersect_domain(SrcDomain).intersect_range(DstDomain);
}

/// If @p PA is k + c for a one-dimensional statement, return c.
static std::optional<int64_t> getUnitStrideConstant(isl::pw_aff PA) {
  if (unsignedFromIslSize(PA.n_piece()) != 1)
    return std::nullopt;
  isl::aff Aff;
  PA.foreach_piece([&](isl::set, isl::aff A) -> isl::stat {
    Aff = A;
    return isl::stat::ok();
  });
  if (Aff.is_null() || unsignedFromIslSize(Aff.dim(isl::dim::in)) != 1 ||
      unsignedFromIslSize(Aff.dim(isl::dim::div)) != 0)
    return std::nullopt;

  auto Coeff = [&](isl_dim_type Type, int Pos) {
    return isl::manage(isl_aff_get_coefficient_val(Aff.get(), Type, Pos));
  };
  for (unsigned P = 0; P < unsignedFromIslSize(Aff.dim(isl::dim::param)); ++P)
    if (!Coeff(isl_dim_param, P).is_zero())
      return std::nullopt;
  if (!Coeff(isl_dim_in, 0).is_one())
    return std::nullopt;
  return getSmallInt(Aff.constant_val());
}

std::optional<int64_t>
polly::getLogicalMisalignment(isl::union_pw_aff Outer,
                              const LogicalOffsetFn &GetLogicalOffset) {
  if (Outer.is_null() || !GetLogicalOffset)
    return std::nullopt;

  std::optional<int64_t> Common;
  bool Failed = false;
  Outer.foreach_pw_aff([&](isl::pw_aff PA) -> isl::stat {
    if (Failed)
      return isl::stat::ok();
    std::optional<int64_t> C = getUnitStrideConstant(PA);
    std::optional<int64_t> Delta;
    if (isl_pw_aff_has_tuple_id(PA.get(), isl_dim_in) == isl_bool_true)
      Delta = GetLogicalOffset(
          isl::manage(isl_pw_aff_get_tuple_id(PA.get(), isl_dim_in)));
    if (!C || !Delta || (Common && *Common != *C - *Delta))
      Failed = true;
    else
      Common = *C - *Delta;
    return isl::stat::ok();
  });
  if (Failed)
    return std::nullopt;
  return Common;
}

std::optional<int64_t> polly::getMinimalLegalShift(isl::union_pw_aff LHSOuter,
                                                   isl::union_pw_aff RHSOuter,
                                                   isl::union_map Deps) {
  if (LHSOuter.is_null() || RHSOuter.is_null() || Deps.is_null())
    return std::nullopt;

  // Dependences from LHS to RHS statements. { LHSDomain[] -> RHSDomain[] }
  isl::union_map D = Deps.intersect_domain(LHSOuter.domain())
                         .intersect_range(RHSOuter.domain());
  if (D.is_empty())
    return 0;

  // { [LHS time] -> [RHS time] } for every dependence.
  isl::union_map T = D.apply_domain(LHSOuter.as_union_map())
                         .apply_range(RHSOuter.as_union_map());

  // RHS time - LHS time for every dependence. After shifting RHS by Δ, every
  // difference must be non-negative: Δ >= -min(Deltas).
  isl::set Deltas = isl::set(T.deltas());
  isl::val Min = Deltas.dim_min_val(0);
  std::optional<int64_t> MinInt = getSmallInt(Min);
  if (!MinInt)
    return std::nullopt;
  return std::max<int64_t>(0, -*MinInt);
}
