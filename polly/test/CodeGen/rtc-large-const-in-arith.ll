; RUN: opt %loadNPMPolly '-passes=polly-custom<ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=AST
; RUN: opt %loadNPMPolly '-passes=polly<no-default-opts>' -S < %s | FileCheck %s
; RUN: opt %loadNPMPolly '-passes=polly<no-default-opts>' -debug-only=polly-codegen -disable-output < %s 2>&1 | FileCheck %s --check-prefix=DEBUG
; REQUIRES: asserts
;
; The run-time check contains a constant that does not fit into 64 bit as an
; operand of an addition. Computing it would require arithmetic with overflow
; tracking on a type wider than 64 bit, which might need runtime library calls.
; Make sure we bail out and do not execute the optimized code.
;
; void g(float *a, long n) {
;   for (float *p = a; p != a - n; --p)
;     *p = 1.0f;
; }
;
; AST: if (1 && 0 == (4 * n >= a + 9223372036854775809 || n >= 2305843009213693953 || n <= 0))
;
; CHECK: br i1 false, label %polly.start, label %for.body.pre_entry_bb
;
; DEBUG: Run-time check has integers larger than 64 bit, optimized code will not be executed

define void @g(ptr %a, i64 %n) {
entry:
  %.neg = mul i64 %n, -4
  %add.ptr = getelementptr inbounds i8, ptr %a, i64 %.neg
  %cmp.not4 = icmp eq i64 %.neg, 0
  br i1 %cmp.not4, label %for.cond.cleanup, label %for.body

for.cond.cleanup:
  ret void

for.body:
  %p.05 = phi ptr [ %incdec.ptr, %for.body ], [ %a, %entry ]
  store float 1.000000e+00, ptr %p.05, align 4
  %incdec.ptr = getelementptr inbounds i8, ptr %p.05, i64 -4
  %cmp.not = icmp eq ptr %incdec.ptr, %add.ptr
  br i1 %cmp.not, label %for.cond.cleanup, label %for.body
}
