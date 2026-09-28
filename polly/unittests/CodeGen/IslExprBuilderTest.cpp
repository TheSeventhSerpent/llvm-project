//===- IslExprBuilderTest.cpp ---------------------------------------------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "polly/CodeGen/IslExprBuilder.h"
#include "gtest/gtest.h"
#include "isl/ast.h"
#include "isl/ctx.h"
#include "isl/id.h"
#include "isl/val.h"

using namespace polly;

namespace {

/// Create the integer 2^Exp + Add.
isl_ast_expr *pow2(isl_ctx *Ctx, long Exp, long Add = 0) {
  isl_val *V = isl_val_2exp(isl_val_int_from_si(Ctx, Exp));
  V = isl_val_add(V, isl_val_int_from_si(Ctx, Add));
  return isl_ast_expr_from_val(V);
}

/// Create the integer -2^Exp.
isl_ast_expr *negPow2(isl_ctx *Ctx, long Exp) {
  isl_val *V = isl_val_2exp(isl_val_int_from_si(Ctx, Exp));
  return isl_ast_expr_from_val(isl_val_neg(V));
}

isl_ast_expr *intExpr(isl_ctx *Ctx, long Val) {
  return isl_ast_expr_from_val(isl_val_int_from_si(Ctx, Val));
}

isl_ast_expr *idExpr(isl_ctx *Ctx, const char *Name) {
  return isl_ast_expr_from_id(isl_id_alloc(Ctx, Name, nullptr));
}

bool hasLargeInts(isl_ast_expr *Expr) {
  return IslExprBuilder::hasLargeInts(isl::manage(Expr));
}

TEST(IslExprBuilder, HasLargeInts) {
  isl_ctx *Ctx = isl_ctx_alloc();

  // Constants that fit into 64 signed bits.
  EXPECT_FALSE(hasLargeInts(intExpr(Ctx, 42)));
  EXPECT_FALSE(hasLargeInts(pow2(Ctx, 63, -1)));
  EXPECT_FALSE(hasLargeInts(negPow2(Ctx, 63)));
  EXPECT_FALSE(
      hasLargeInts(isl_ast_expr_add(idExpr(Ctx, "p"), negPow2(Ctx, 63))));
  EXPECT_FALSE(
      hasLargeInts(isl_ast_expr_add(idExpr(Ctx, "p"), pow2(Ctx, 63, -1))));

  // Constants that need more than 64 signed bits.
  EXPECT_TRUE(hasLargeInts(pow2(Ctx, 63)));
  EXPECT_TRUE(hasLargeInts(negPow2(Ctx, 64)));
  EXPECT_TRUE(hasLargeInts(isl_ast_expr_neg(pow2(Ctx, 63))));
  EXPECT_TRUE(hasLargeInts(isl_ast_expr_add(idExpr(Ctx, "p"), pow2(Ctx, 63))));
  EXPECT_TRUE(hasLargeInts(isl_ast_expr_mul(pow2(Ctx, 64), idExpr(Ctx, "n"))));

  // A wide constant directly compared against 64-bit arithmetic is fine:
  //   4 * n + p >= 2^63 + 4
  isl_ast_expr *Sum = isl_ast_expr_add(
      isl_ast_expr_mul(intExpr(Ctx, 4), idExpr(Ctx, "n")), idExpr(Ctx, "p"));
  EXPECT_FALSE(hasLargeInts(isl_ast_expr_ge(Sum, pow2(Ctx, 63, 4))));
  EXPECT_FALSE(hasLargeInts(isl_ast_expr_le(pow2(Ctx, 100), idExpr(Ctx, "n"))));

  // ... also when nested in a boolean expression.
  EXPECT_FALSE(hasLargeInts(
      isl_ast_expr_or(isl_ast_expr_ge(idExpr(Ctx, "n"), pow2(Ctx, 63)),
                      isl_ast_expr_le(idExpr(Ctx, "n"), intExpr(Ctx, 0)))));

  // A wide constant inside arithmetic under a comparison is still rejected.
  EXPECT_TRUE(hasLargeInts(isl_ast_expr_ge(
      isl_ast_expr_add(idExpr(Ctx, "p"), pow2(Ctx, 63)), intExpr(Ctx, 0))));

  isl_ctx_free(Ctx);
}

} // anonymous namespace
