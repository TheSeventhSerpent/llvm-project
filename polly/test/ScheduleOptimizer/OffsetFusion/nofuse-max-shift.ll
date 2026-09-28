; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-max-shift=16 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s --check-prefix=MAX16
;
; Aligning the loops needs a shift of 10, more than the default maximum of 4.
;
; void maxshift(long n, float *restrict A, float *restrict B, float *restrict C) {
;   for (long i = 0; i < n; i++)  B[i] = A[i] * 2;
;   for (long i = 10; i < n; i++) C[i] = B[i] + 1;
; }

define void @maxshift(i64 %n, ptr %A, ptr %B, ptr %C) {
entry:
  %cmp20 = icmp sgt i64 %n, 0
  br i1 %cmp20, label %for.body, label %for.cond.cleanup5

for.cond3.preheader:
  %cmp422 = icmp samesign ugt i64 %n, 10
  br i1 %cmp422, label %for.body6, label %for.cond.cleanup5

for.body:
  %i.021 = phi i64 [ %inc, %for.body ], [ 0, %entry ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i.021
  %0 = load float, ptr %arrayidx, align 4
  %mul = fmul float %0, 2.000000e+00
  %arrayidx1 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i.021
  store float %mul, ptr %arrayidx1, align 4
  %inc = add nuw nsw i64 %i.021, 1
  %exitcond.not = icmp eq i64 %inc, %n
  br i1 %exitcond.not, label %for.cond3.preheader, label %for.body

for.cond.cleanup5:
  ret void

for.body6:
  %i2.023 = phi i64 [ %inc10, %for.body6 ], [ 10, %for.cond3.preheader ]
  %arrayidx7 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i2.023
  %1 = load float, ptr %arrayidx7, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx8 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i2.023
  store float %add, ptr %arrayidx8, align 4
  %inc10 = add nuw nsw i64 %i2.023, 1
  %exitcond24.not = icmp eq i64 %inc10, %n
  br i1 %exitcond24.not, label %for.cond.cleanup5, label %for.body6
}

; CHECK:     Calculated schedule:
; CHECK-NOT: Offset-aware fusion

; MAX16:      mark: "Offset-aware fusion"
; MAX16-NEXT: child:
; MAX16-NEXT:   schedule: "[n] -> [{ Stmt_for_body6[i0] -> [(10 + i0)]; Stmt_for_body[i0] -> [(i0)] }]"
