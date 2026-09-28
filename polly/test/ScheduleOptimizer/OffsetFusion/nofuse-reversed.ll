; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
;
; The second loop traverses B backwards. The required shift grows with n,
; so the loops are not fused.
;
; void reversed(long n, float *restrict A, float *restrict B, float *restrict C) {
;   for (long i = 0; i < n; i++) B[i] = A[i] * 2;
;   for (long k = 0; k < n; k++) C[k] = B[n - 1 - k] + 1;
; }

define void @reversed(i64 %n, ptr %A, ptr %B, ptr %C) {
entry:
  %cmp21 = icmp sgt i64 %n, 0
  br i1 %cmp21, label %for.body, label %for.cond.cleanup4

for.body5.lr.ph:
  %0 = getelementptr [4 x i8], ptr %B, i64 %n
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
  br i1 %exitcond.not, label %for.body5.lr.ph, label %for.body

for.cond.cleanup4:
  ret void

for.body5:
  %k.024 = phi i64 [ 0, %for.body5.lr.ph ], [ %inc10, %for.body5 ]
  %2 = xor i64 %k.024, -1
  %arrayidx7 = getelementptr [4 x i8], ptr %0, i64 %2
  %3 = load float, ptr %arrayidx7, align 4
  %add = fadd float %3, 1.000000e+00
  %arrayidx8 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %k.024
  store float %add, ptr %arrayidx8, align 4
  %inc10 = add nuw nsw i64 %k.024, 1
  %exitcond25.not = icmp eq i64 %inc10, %n
  br i1 %exitcond25.not, label %for.cond.cleanup4, label %for.body5
}

; CHECK:     Calculated schedule:
; CHECK-NOT: Offset-aware fusion
