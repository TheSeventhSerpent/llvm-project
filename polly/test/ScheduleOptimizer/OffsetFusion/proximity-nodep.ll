; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<opt-isl>' -debug-only=polly-opt-isl -disable-output < %s 2>&1 | FileCheck %s --check-prefix=DEBUG
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-unserialize -polly-postopts=0 '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=FUSED
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-unserialize -polly-offset-fusion-proximity=0 -polly-postopts=0 '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=SEPARATE
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-postopts=0 '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=SEPARATE
; REQUIRES: asserts
;
; Two loops without any dependence between them read the same array at
; logical offsets 0 and 1. Offset proximity is the only relation between them.
; If isl does not serialize strongly connected components, it uses the
; relation to fuse the loops, aligned by their logical index.
;
; void g(long n, float *restrict A, float *restrict B, float *restrict C) {
;   for (long i = 0; i < n; i++) B[i] = A[i] * 2;
;   for (long i = 1; i < n; i++) C[i] = A[i] + 1;
; }

define void @g(i64 %n, ptr %A, ptr %B, ptr %C) {
entry:
  %cmp20 = icmp sgt i64 %n, 0
  br i1 %cmp20, label %for.body, label %for.cond.cleanup5

for.cond3.preheader:
  %cmp422.not = icmp eq i64 %n, 1
  br i1 %cmp422.not, label %for.cond.cleanup5, label %for.body6

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
  %i2.023 = phi i64 [ %inc10, %for.body6 ], [ 1, %for.cond3.preheader ]
  %arrayidx7 = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i2.023
  %1 = load float, ptr %arrayidx7, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx8 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i2.023
  store float %add, ptr %arrayidx8, align 4
  %inc10 = add nuw nsw i64 %i2.023, 1
  %exitcond24.not = icmp eq i64 %inc10, %n
  br i1 %exitcond24.not, label %for.cond.cleanup5, label %for.body6
}

; DEBUG: Offset proximity := [n] -> { Stmt_for_body[i0] -> Stmt_for_body6[-1 + i0] : 0 < i0 < n };
; DEBUG: Validity := [n] -> {  };

; FUSED:      for (int c0 = 0; c0 < n; c0 += 1) {
; FUSED-NEXT:   Stmt_for_body(c0);
; FUSED-NEXT:   if (c0 >= 1)
; FUSED-NEXT:     Stmt_for_body6(c0 - 1);
; FUSED-NEXT: }

; SEPARATE:      for (int c0 = 0; c0 < n; c0 += 1)
; SEPARATE-NEXT:   Stmt_for_body(c0);
; SEPARATE:      for (int c0 = 0; c0 < n - 1; c0 += 1)
; SEPARATE-NEXT:   Stmt_for_body6(c0);
