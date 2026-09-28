; RUN: opt %loadNPMPolly -S '-passes=polly<no-default-opts>' -polly-annotate-metadata-vectorize < %s | FileCheck %s
; RUN: opt %loadNPMPolly -S '-passes=polly<no-default-opts>' < %s | FileCheck %s

; Verify vectorization is not disabled when RTC of Polly is false

; The RTC is false because it contains a constant that does not fit into 64 bit
; as an operand of an addition:
;   4 * n >= a + 9223372036854775809
;
; CHECK: br i1 false, label %polly.start
; CHECK: attributes {{.*}} = { "polly-optimized" }
; CHECK-NOT: {{.*}} = !{!"llvm.loop.vectorize.disable"}

target datalayout = "e-m:e-i8:8:32-i16:16:32-i64:64-i128:128-n32:64-S128-Fn32"
target triple = "aarch64-unknown-linux-android10000"

define void @ham(ptr %a, i64 %n) {
entry:
  %neg = mul i64 %n, -4
  %end = getelementptr inbounds i8, ptr %a, i64 %neg
  %cmp.entry = icmp eq i64 %neg, 0
  br i1 %cmp.entry, label %exit, label %loop

loop:
  %p = phi ptr [ %p.next, %loop ], [ %a, %entry ]
  store float 1.000000e+00, ptr %p, align 4
  %p.next = getelementptr inbounds i8, ptr %p, i64 -4
  %cmp = icmp eq ptr %p.next, %end
  br i1 %cmp, label %exit, label %loop

exit:
  ret void
}
