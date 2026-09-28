; RUN: opt %loadNPMPolly '-passes=polly-custom<ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=AST
; RUN: opt %loadNPMPolly '-passes=polly<no-default-opts>' -S < %s | FileCheck %s
; RUN: opt %loadNPMPolly '-passes=polly<no-default-opts>' -S < %s | FileCheck %s --check-prefix=NOWIDE
;
; The run-time check of a loop over a pointer with a 64-bit trip count contains
; the no-overflow assumption a + 4 * n >= 2^63. The constant 2^63 does not fit
; into i64. Make sure that we still generate a run-time check instead of
; disabling the optimized code: only the comparison is performed in i65, the
; address computation itself stays in i64 with overflow tracking.
;
; void f(float *a, long n) {
;   for (float *p = a; p != a + n; ++p)
;     *p = 1.0f;
; }
;
; AST: if (1 && 0 == (a + 4 * n >= 9223372036854775808 || n >= 2305843009213693952 || n <= 0))
;
; CHECK:      %[[PTR:.*]] = ptrtoint ptr %a to i64
; CHECK:      %[[MUL:.*]] = call { i64, i1 } @llvm.smul.with.overflow.i64(i64 4, i64 %n)
; CHECK:      %[[MULRES:.*]] = extractvalue { i64, i1 } %[[MUL]], 0
; CHECK:      %[[ADD:.*]] = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %[[PTR]], i64 %[[MULRES]])
; CHECK:      %[[ADDRES:.*]] = extractvalue { i64, i1 } %[[ADD]], 0
; CHECK-NEXT: %[[EXT:.*]] = sext i64 %[[ADDRES]] to i65
; CHECK-NEXT: icmp sge i65 %[[EXT]], 9223372036854775808
; CHECK:      %polly.rtc.result = and i1 %{{.*}}, %polly.rtc.overflown
; CHECK-NEXT: br i1 %polly.rtc.result, label %polly.start, label %for.body.pre_entry_bb
;
; No arithmetic is performed on types wider than 64 bit.
; NOWIDE-NOT: with.overflow.i{{(6[5-9]|[7-9][0-9]|[1-9][0-9][0-9])}}

define void @f(ptr %a, i64 %n) {
entry:
  %add.ptr.idx = shl nsw i64 %n, 2
  %add.ptr = getelementptr inbounds i8, ptr %a, i64 %add.ptr.idx
  %cmp.not4 = icmp eq i64 %n, 0
  br i1 %cmp.not4, label %for.cond.cleanup, label %for.body

for.cond.cleanup:
  ret void

for.body:
  %p.05 = phi ptr [ %incdec.ptr, %for.body ], [ %a, %entry ]
  store float 1.000000e+00, ptr %p.05, align 4
  %incdec.ptr = getelementptr inbounds nuw i8, ptr %p.05, i64 4
  %cmp.not = icmp eq ptr %incdec.ptr, %add.ptr
  br i1 %cmp.not, label %for.cond.cleanup, label %for.body
}
