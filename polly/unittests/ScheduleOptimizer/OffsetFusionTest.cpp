//===- OffsetFusionTest.cpp -----------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "polly/Support/OffsetFusion.h"
#include "polly/ScheduleTreeTransform.h"
#include "polly/Support/GICHelper.h"
#include "gtest/gtest.h"
#include "isl/ctx.h"
#include "isl/options.h"
#include <map>
#include <string>

using namespace polly;

namespace {

/// Allocate an isl_ctx that aborts on errors, as Polly's does by default
/// (-polly-on-isl-error-abort).
isl_ctx *allocAbortingCtx() {
  isl_ctx *Ctx = isl_ctx_alloc();
  isl_options_set_on_error(Ctx, ISL_ON_ERROR_ABORT);
  return Ctx;
}

TEST(OffsetFusion, getOffsetFromAccess) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    isl::set Dom(Ctx, "[n] -> { S[k] : 0 <= k < n - 1 }");
    auto Offset = [&](const char *Access) {
      return getOffsetFromAccess(Dom, isl::map(Ctx, Access));
    };

    EXPECT_EQ(std::optional<int64_t>(1), Offset("{ S[k] -> M[k + 1] }"));
    EXPECT_EQ(std::optional<int64_t>(0), Offset("{ S[k] -> M[k] }"));
    EXPECT_EQ(std::optional<int64_t>(-2), Offset("{ S[k] -> M[k - 2] }"));
    EXPECT_EQ(std::optional<int64_t>(1),
              Offset("[n] -> { S[k] -> M[k + 1] : n >= 5 }"));

    // Stride 2, base 2: element 2 * (k + 1).
    EXPECT_EQ(std::optional<int64_t>(1), Offset("{ S[k] -> M[2k + 2] }"));

    // Base not divisible by the stride.
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[2k + 1] }"));

    // Parametric offset.
    EXPECT_EQ(std::nullopt, Offset("[n] -> { S[k] -> M[k + n] }"));

    // Stride 0.
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[5] }"));

    // Negative stride (reversed traversal).
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[3 - k] }"));

    // Integer division.
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[floor(k / 2)] }"));

    // Multi-dimensional array.
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[k, 0] }"));

    // Not single-valued.
    EXPECT_EQ(std::nullopt, Offset("{ S[k] -> M[i] : k <= i <= k + 1 }"));
  }

  {
    // Multi-dimensional statement.
    isl::set Dom(Ctx, "[n] -> { S[i, j] : 0 <= i, j < n }");
    EXPECT_EQ(std::nullopt,
              getOffsetFromAccess(Dom, isl::map(Ctx, "{ S[i, j] -> M[i] }")));
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, shiftDomain) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    isl::set Dom(Ctx, "[n] -> { S[k] : 0 <= k < n - 1 }");
    EXPECT_TRUE(shiftDomain(Dom, 1).is_equal(
        isl::set(Ctx, "[n] -> { S[k] : 1 <= k < n }")));
    EXPECT_TRUE(shiftDomain(Dom, -2).is_equal(
        isl::set(Ctx, "[n] -> { S[k] : -2 <= k < n - 3 }")));
    EXPECT_TRUE(shiftDomain(Dom, 0).is_equal(Dom));
  }

  {
    isl::set Dom(Ctx, "{ S[k] : 0 <= k < 10 }");
    isl::map P2L = physicalToLogical(Dom.get_space(), 3);
    EXPECT_TRUE(P2L.is_equal(isl::map(Ctx, "{ S[k] -> S[k + 3] }")));
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, areShiftCompatible) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    isl::set Context(Ctx, "[N] -> { : N >= 0 }");
    isl::set S0(Ctx, "[N] -> { S0[i] : 0 <= i < N }");
    isl::set S1(Ctx, "[N] -> { S1[i] : 1 <= i < N }");
    isl::set S2(Ctx, "[N] -> { S2[i] : 0 <= i < N - 1 }");

    // Example from the thesis: all pairs are compatible.
    EXPECT_TRUE(areShiftCompatible(S0, S1, Context));
    EXPECT_TRUE(areShiftCompatible(S1, S0, Context));
    EXPECT_TRUE(areShiftCompatible(S0, S2, Context));
    EXPECT_TRUE(areShiftCompatible(S1, S2, Context));
    EXPECT_TRUE(areShiftCompatible(S0, S0, Context));

    // The upper bounds differ by N.
    isl::set Double(Ctx, "[N] -> { S3[i] : 0 <= i < 2N }");
    EXPECT_FALSE(areShiftCompatible(Double, S0, Context));

    // No upper bound.
    isl::set Unbounded(Ctx, "[N] -> { S4[i] : i >= 0 }");
    EXPECT_FALSE(areShiftCompatible(Unbounded, S0, Context));

    // Multi-dimensional.
    isl::set TwoD(Ctx, "[N] -> { S5[i, j] : 0 <= i, j < N }");
    EXPECT_FALSE(areShiftCompatible(TwoD, TwoD, Context));
  }

  {
    // Disjoint ranges.
    isl::set Context(Ctx, "{ : }");
    isl::set A(Ctx, "{ A[i] : 0 <= i < 5 }");
    isl::set B(Ctx, "{ B[i] : 10 <= i < 20 }");
    EXPECT_FALSE(areShiftCompatible(A, B, Context));
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, getOffsetProximity) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    isl::set Context(Ctx, "[N] -> { : N >= 0 }");
    // Loops over [0, N), [1, N) and [0, N - 1) with physical iterators.
    isl::set S0(Ctx, "[N] -> { S0[i] : 0 <= i < N }");
    isl::set S1(Ctx, "[N] -> { S1[i] : 0 <= i < N - 1 }");
    isl::set S2(Ctx, "[N] -> { S2[i] : 0 <= i < N - 1 }");

    // S0[i] and S1[i - 1] process logical index i.
    isl::map R01 = getOffsetProximity(S0, 0, S1, 1, Context);
    EXPECT_TRUE(R01.is_equal(
        isl::map(Ctx, "[N] -> { S0[i] -> S1[i - 1] : 1 <= i < N }")));

    isl::map R02 = getOffsetProximity(S0, 0, S2, 0, Context);
    EXPECT_TRUE(R02.is_equal(
        isl::map(Ctx, "[N] -> { S0[i] -> S2[i] : 0 <= i < N - 1 }")));

    isl::map R12 = getOffsetProximity(S1, 1, S2, 0, Context);
    EXPECT_TRUE(R12.is_equal(
        isl::map(Ctx, "[N] -> { S1[i] -> S2[i + 1] : 0 <= i < N - 2 }")));
  }

  {
    // Not shift-compatible: the upper bounds differ by N.
    isl::set Context(Ctx, "[N] -> { : N >= 0 }");
    isl::set A(Ctx, "[N] -> { A[i] : 0 <= i < 2N }");
    isl::set B(Ctx, "[N] -> { B[i] : 0 <= i < N }");
    EXPECT_TRUE(getOffsetProximity(A, 0, B, 0, Context).is_null());
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, getMinimalLegalShift) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    isl::union_pw_aff L(Ctx, "[n] -> { S0[i] -> [(i)] }");
    isl::union_pw_aff R(Ctx, "[n] -> { S1[k] -> [(k)] }");
    auto Shift = [&](const char *Deps) {
      return getMinimalLegalShift(L, R, isl::union_map(Ctx, Deps));
    };

    // S1[i - 1] reads what S0[i] writes: S1 must be delayed by one iteration.
    EXPECT_EQ(std::optional<int64_t>(1),
              Shift("[n] -> { S0[i] -> S1[i - 1] : 1 <= i < n }"));

    // No dependences.
    EXPECT_EQ(std::optional<int64_t>(0), Shift("[n] -> { }"));

    // Dependences only between other statements.
    EXPECT_EQ(std::optional<int64_t>(0),
              Shift("[n] -> { S1[i] -> S0[i + 1] : 0 <= i < n }"));

    // Dependences that are already satisfied without a shift.
    EXPECT_EQ(std::optional<int64_t>(0),
              Shift("[n] -> { S0[i] -> S1[i + 2] : 0 <= i < n }"));

    // Reversed access: the required shift grows with n.
    EXPECT_EQ(std::nullopt,
              Shift("[n] -> { S0[i] -> S1[n - 1 - i] : 0 <= i < n }"));
  }

  isl_ctx_free(Ctx);
}

/// Logical offsets by statement name.
LogicalOffsetFn
offsetsByName(std::map<std::string, std::optional<int64_t>> Offsets) {
  return [Offsets](const isl::id &Id) -> std::optional<int64_t> {
    auto It = Offsets.find(Id.name());
    return It == Offsets.end() ? std::nullopt : It->second;
  };
}

TEST(OffsetFusion, getLogicalMisalignment) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    LogicalOffsetFn Offsets = offsetsByName({{"S0", 0}, {"S1", 1}, {"S2", 0}});

    // m = c - δ.
    EXPECT_EQ(std::optional<int64_t>(0),
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S0[i] -> [(i)] }"), Offsets));
    EXPECT_EQ(std::optional<int64_t>(-1),
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S1[i] -> [(i)] }"), Offsets));
    EXPECT_EQ(std::optional<int64_t>(0),
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S1[i] -> [(i + 1)] }"), Offsets));

    // All statements agree.
    EXPECT_EQ(
        std::optional<int64_t>(0),
        getLogicalMisalignment(
            isl::union_pw_aff(Ctx, "{ S0[i] -> [(i)]; S1[i] -> [(i + 1)] }"),
            Offsets));

    // Statements disagree.
    EXPECT_EQ(std::nullopt,
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S0[i] -> [(i)]; S1[i] -> [(i)] }"),
                  Offsets));

    // Not of the form k + c.
    EXPECT_EQ(std::nullopt,
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S0[i] -> [(2i)] }"), Offsets));
    EXPECT_EQ(
        std::nullopt,
        getLogicalMisalignment(
            isl::union_pw_aff(Ctx, "[n] -> { S0[i] -> [(i + n)] }"), Offsets));

    // Unknown offset.
    EXPECT_EQ(std::nullopt,
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S3[i] -> [(i)] }"), Offsets));

    // No callback.
    EXPECT_EQ(std::nullopt,
              getLogicalMisalignment(
                  isl::union_pw_aff(Ctx, "{ S0[i] -> [(i)] }"), {}));
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, applyGreedyFusionWithShift) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    // Two loops over [0, n) and [0, n - 1). S1[i] depends on S0[i + 1].
    isl::schedule Sched(
        Ctx, "{ domain: \"[n] -> { S0[i] : 0 <= i < n; S1[i] : 0 <= i < n - "
             "1 }\", child: { sequence: [ { filter: \"{ S0[i] }\", child: { "
             "schedule: \"[n] -> [{ S0[i] -> [(i)] }]\" } }, { filter: \"{ "
             "S1[i] }\", child: { schedule: \"[n] -> [{ S1[i] -> [(i)] }]\" "
             "} } ] } }");
    isl::union_map Deps(Ctx, "[n] -> { S0[i] -> S1[i - 1] : 1 <= i < n }");

    GreedyFusionOptions Opts;
    Opts.AllowShift = true;
    Opts.MarkFused = true;
    Opts.MaxShift = 4;

    // Plain fusion is illegal; the shift is derived from the dependences.
    isl::schedule Fused = applyGreedyFusion(Sched, Deps, Opts);
    EXPECT_TRUE(Fused.get_map().is_equal(isl::union_map(
        Ctx, "[n] -> { S0[i] -> [i, 0]; S1[i] -> [i + 1, 1] }")));
    isl::schedule_node Mark = Fused.get_root().child(0);
    ASSERT_EQ(isl_schedule_node_mark, isl_schedule_node_get_type(Mark.get()));
    EXPECT_EQ(std::string(OffsetFusionMarkName),
              Mark.as<isl::schedule_node_mark>().get_id().name());

    // Logical alignment takes precedence if it is legal: S1 processes the
    // logical index i + 2.
    Opts.GetLogicalOffset = offsetsByName({{"S0", 0}, {"S1", 2}});
    Fused = applyGreedyFusion(Sched, Deps, Opts);
    EXPECT_TRUE(Fused.get_map().is_equal(isl::union_map(
        Ctx, "[n] -> { S0[i] -> [i, 0]; S1[i] -> [i + 2, 1] }")));

    // ... unless the shift is too large.
    Opts.MaxShift = 1;
    Fused = applyGreedyFusion(Sched, Deps, Opts);
    EXPECT_TRUE(Fused.get_map().is_equal(isl::union_map(
        Ctx, "[n] -> { S0[i] -> [i, 0]; S1[i] -> [i + 1, 1] }")));

    // Without shifting, the loops are not fused.
    Fused = applyGreedyFusion(Sched, Deps, GreedyFusionOptions());
    EXPECT_TRUE(Fused.get_map().is_equal(Sched.get_map()));
  }

  isl_ctx_free(Ctx);
}

TEST(OffsetFusion, isolateOffsetFusedBands) {
  isl_ctx *Ctx = allocAbortingCtx();

  {
    // The diploma example after offset-aware fusion.
    auto MakeSched = [&](bool HasMark, const char *Domain) {
      std::string Band =
          "{ schedule: \"[n] -> [{ S0[i] -> [(i)]; S1[i] -> [(i + 1)]; S2[i] "
          "-> [(i)] }]\", child: { sequence: [ { filter: \"{ S0[i] }\" }, { "
          "filter: \"{ S1[i] }\" }, { filter: \"{ S2[i] }\" } ] } }";
      if (HasMark)
        Band = "{ mark: \"Offset-aware fusion\", child: " + Band + " }";
      return isl::schedule(Ctx, std::string("{ domain: \"") + Domain +
                                    "\", child: " + Band + " }");
    };
    const char *Shifted = "[n] -> { S0[i] : 0 <= i < n; S1[i] : 0 <= i < n - "
                          "1; S2[i] : 0 <= i < n - 1 }";
    auto GetOptions = [](isl::schedule Sched, bool HasMark) {
      isl::schedule_node Band = Sched.get_root().child(0);
      if (HasMark)
        Band = Band.child(0);
      return Band.as<isl::schedule_node_band>().get_ast_build_options();
    };

    // All loop bodies are executed in 1 <= i <= n - 2.
    isl::schedule Isolated = isolateOffsetFusedBands(MakeSched(true, Shifted));
    isl::union_set Expected(
        Ctx, "[n] -> { isolate[[] -> [i]] : 1 <= i <= n - 2; atomic[0] }");
    EXPECT_TRUE(GetOptions(Isolated, true).is_equal(Expected))
        << stringFromIslObj(GetOptions(Isolated, true));

    // Bands without the mark are not changed.
    isl::schedule Unmarked = isolateOffsetFusedBands(MakeSched(false, Shifted));
    EXPECT_TRUE(GetOptions(Unmarked, false).is_empty());

    // Nothing to isolate if all bodies are executed in all iterations.
    isl::schedule Equal = isolateOffsetFusedBands(MakeSched(
        true, "[n] -> { S0[i] : 1 <= i < n - 1; S1[i] : 0 <= i < n - 2; "
              "S2[i] : 1 <= i < n - 1 }"));
    EXPECT_TRUE(GetOptions(Equal, true).is_empty());
  }

  isl_ctx_free(Ctx);
}

} // anonymous namespace
