; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
;
; The offset of the second loop depends on the parameter m. It has no logical
; offset and the required shift is unbounded, so the loops are not fused.
;
; void paramoff(long n, long m, float *restrict A, float *restrict B,
;               float *restrict C) {
;   for (long i = 0; i < n; i++) B[i] = A[i] * 2;
;   for (long k = 0; k < n; k++) C[k + m] = B[k + m] + 1;
; }

define void @paramoff(i64 %n, i64 %m, ptr %A, ptr %B, ptr %C) {
entry:
  %cmp22 = icmp sgt i64 %n, 0
  br i1 %cmp22, label %for.body, label %for.cond.cleanup4

for.body:
  %i.023 = phi i64 [ %inc, %for.body ], [ 0, %entry ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i.023
  %0 = load float, ptr %arrayidx, align 4
  %mul = fmul float %0, 2.000000e+00
  %arrayidx1 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i.023
  store float %mul, ptr %arrayidx1, align 4
  %inc = add nuw nsw i64 %i.023, 1
  %exitcond.not = icmp eq i64 %inc, %n
  br i1 %exitcond.not, label %for.body5, label %for.body

for.cond.cleanup4:
  ret void

for.body5:
  %k.025 = phi i64 [ %inc11, %for.body5 ], [ 0, %for.body ]
  %add = add nsw i64 %k.025, %m
  %arrayidx6 = getelementptr inbounds [4 x i8], ptr %B, i64 %add
  %1 = load float, ptr %arrayidx6, align 4
  %add7 = fadd float %1, 1.000000e+00
  %arrayidx9 = getelementptr inbounds [4 x i8], ptr %C, i64 %add
  store float %add7, ptr %arrayidx9, align 4
  %inc11 = add nuw nsw i64 %k.025, 1
  %exitcond26.not = icmp eq i64 %inc11, %n
  br i1 %exitcond26.not, label %for.cond.cleanup4, label %for.body5
}

; CHECK:     Calculated schedule:
; CHECK-NOT: Offset-aware fusion
