; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=PLAIN
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-prefer-aligned '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=ALIGNED
;
; The loops can be fused without a shift: C[i] is then read one iteration
; after it is written. With -polly-offset-fusion-prefer-aligned, the second
; loop is shifted such that C[i] is written and read in the same iteration.
;
; void pair(long n, float *restrict B, float *restrict C, float *restrict D) {
;   for (long i = 1; i < n; i++)     C[i] = B[i] + 1;
;   for (long i = 0; i < n - 1; i++) D[i] = C[i] * 2;
; }

define void @pair(i64 %n, ptr %B, ptr %C, ptr %D) {
entry:
  %cmp20 = icmp sgt i64 %n, 1
  br i1 %cmp20, label %for.body, label %for.cond.cleanup5

for.body6.preheader:
  %0 = add nsw i64 %n, -2
  br label %for.body6

for.body:
  %i.021 = phi i64 [ %inc, %for.body ], [ 1, %entry ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i.021
  %1 = load float, ptr %arrayidx, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx1 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i.021
  store float %add, ptr %arrayidx1, align 4
  %inc = add nuw nsw i64 %i.021, 1
  %exitcond.not = icmp eq i64 %inc, %n
  br i1 %exitcond.not, label %for.body6.preheader, label %for.body

for.cond.cleanup5:
  ret void

for.body6:
  %i2.023 = phi i64 [ %inc10, %for.body6 ], [ 0, %for.body6.preheader ]
  %arrayidx7 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i2.023
  %2 = load float, ptr %arrayidx7, align 4
  %mul = fmul float %2, 2.000000e+00
  %arrayidx8 = getelementptr inbounds nuw [4 x i8], ptr %D, i64 %i2.023
  store float %mul, ptr %arrayidx8, align 4
  %inc10 = add nuw nsw i64 %i2.023, 1
  %exitcond24.not = icmp eq i64 %i2.023, %0
  br i1 %exitcond24.not, label %for.cond.cleanup5, label %for.body6
}

; PLAIN:      // Offset-aware fusion
; PLAIN-NEXT: for (int c0 = 0; c0 < n - 1; c0 += 1) {
; PLAIN-NEXT:   Stmt_for_body(c0);
; PLAIN-NEXT:   Stmt_for_body6(c0);
; PLAIN-NEXT: }

; ALIGNED:      // Offset-aware fusion
; ALIGNED-NEXT: {
; ALIGNED-NEXT:   if (n >= 3)
; ALIGNED-NEXT:     Stmt_for_body6(0);
; ALIGNED-NEXT:   for (int c0 = 0; c0 < n - 2; c0 += 1) {
; ALIGNED-NEXT:     Stmt_for_body(c0);
; ALIGNED-NEXT:     Stmt_for_body6(c0 + 1);
; ALIGNED-NEXT:   }
; ALIGNED-NEXT:   if (n >= 3) {
; ALIGNED-NEXT:     Stmt_for_body(n - 2);
