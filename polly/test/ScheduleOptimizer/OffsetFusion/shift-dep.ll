; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-shift=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s --check-prefix=NOSHIFT
;
; Both statements have logical offset 0 (from their writes), so aligning them
; by their logical index does not help. The shift is derived from the
; dependences instead: B[k + 1] is written one iteration later.
;
; void depshift(long n, float *restrict A, float *restrict B, float *restrict C) {
;   for (long i = 0; i < n; i++)     B[i] = A[i] * 2;
;   for (long k = 0; k < n - 1; k++) C[2 * k] = B[k + 1] + 1;
; }

define void @depshift(i64 %n, ptr %A, ptr %B, ptr %C) {
entry:
  %cmp21 = icmp sgt i64 %n, 0
  br i1 %cmp21, label %for.body, label %for.cond.cleanup4

for.cond2.preheader:
  %cmp323.not = icmp eq i64 %n, 1
  br i1 %cmp323.not, label %for.cond.cleanup4, label %for.body5.preheader

for.body5.preheader:
  %0 = add nsw i64 %n, -2
  br label %for.body5

for.body:
  %i.022 = phi i64 [ %inc, %for.body ], [ 0, %entry ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i.022
  %1 = load float, ptr %arrayidx, align 4
  %mul = fmul float %1, 2.000000e+00
  %arrayidx1 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i.022
  store float %mul, ptr %arrayidx1, align 4
  %inc = add nuw nsw i64 %i.022, 1
  %exitcond.not = icmp eq i64 %inc, %n
  br i1 %exitcond.not, label %for.cond2.preheader, label %for.body

for.cond.cleanup4:
  ret void

for.body5:
  %k.024 = phi i64 [ %add, %for.body5 ], [ 0, %for.body5.preheader ]
  %add = add nuw nsw i64 %k.024, 1
  %arrayidx6 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %add
  %2 = load float, ptr %arrayidx6, align 4
  %add7 = fadd float %2, 1.000000e+00
  %arrayidx9.idx = shl nuw nsw i64 %k.024, 3
  %arrayidx9 = getelementptr inbounds nuw i8, ptr %C, i64 %arrayidx9.idx
  store float %add7, ptr %arrayidx9, align 4
  %exitcond25.not = icmp eq i64 %k.024, %0
  br i1 %exitcond25.not, label %for.cond.cleanup4, label %for.body5
}

; CHECK:      Calculated schedule:
; CHECK:        mark: "Offset-aware fusion"
; CHECK-NEXT:   child:
; CHECK-NEXT:     schedule: "[n] -> [{ Stmt_for_body5[i0] -> [(1 + i0)]; Stmt_for_body[i0] -> [(i0)] }]"
; CHECK-NEXT:     child:
; CHECK-NEXT:       sequence:
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body[i0] }"
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body5[i0] }"

; NOSHIFT:     Calculated schedule:
; NOSHIFT-NOT: Offset-aware fusion
