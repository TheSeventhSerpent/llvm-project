; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-loopfusion-greedy '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=GREEDY
;
; Offset-aware fusion only fuses one-dimensional loops. Loop nests keep their
; schedule, which remains tileable. With -polly-loopfusion-greedy, all loops
; are fused as before.
;
; void nest(float A[restrict 64][64], float B[restrict 64][64],
;           float C[restrict 64][64]) {
;   for (int i = 0; i < 64; i++)
;     for (int j = 0; j < 64; j++)
;       B[i][j] = A[i][j] * 2;
;   for (int i = 0; i < 64; i++)
;     for (int j = 0; j < 64; j++)
;       C[i][j] = B[i][j] + 1;
; }

define void @nest(ptr %A, ptr %B, ptr %C) {
entry:
  br label %for.cond1.preheader

for.cond1.preheader:
  %indvars.iv56 = phi i64 [ 0, %entry ], [ %indvars.iv.next57, %for.cond.cleanup3 ]
  %arrayidx = getelementptr inbounds nuw [256 x i8], ptr %A, i64 %indvars.iv56
  %arrayidx8 = getelementptr inbounds nuw [256 x i8], ptr %B, i64 %indvars.iv56
  br label %for.body4

for.cond.cleanup3:
  %indvars.iv.next57 = add nuw nsw i64 %indvars.iv56, 1
  %exitcond59.not = icmp eq i64 %indvars.iv.next57, 64
  br i1 %exitcond59.not, label %for.cond20.preheader, label %for.cond1.preheader

for.body4:
  %indvars.iv = phi i64 [ 0, %for.cond1.preheader ], [ %indvars.iv.next, %for.body4 ]
  %arrayidx6 = getelementptr inbounds nuw [4 x i8], ptr %arrayidx, i64 %indvars.iv
  %0 = load float, ptr %arrayidx6, align 4
  %mul = fmul float %0, 2.000000e+00
  %arrayidx10 = getelementptr inbounds nuw [4 x i8], ptr %arrayidx8, i64 %indvars.iv
  store float %mul, ptr %arrayidx10, align 4
  %indvars.iv.next = add nuw nsw i64 %indvars.iv, 1
  %exitcond.not = icmp eq i64 %indvars.iv.next, 64
  br i1 %exitcond.not, label %for.cond.cleanup3, label %for.body4

for.cond20.preheader:
  %indvars.iv64 = phi i64 [ %indvars.iv.next65, %for.cond.cleanup22 ], [ 0, %for.cond.cleanup3 ]
  %arrayidx25 = getelementptr inbounds nuw [256 x i8], ptr %B, i64 %indvars.iv64
  %arrayidx29 = getelementptr inbounds nuw [256 x i8], ptr %C, i64 %indvars.iv64
  br label %for.body23

for.cond.cleanup17:
  ret void

for.cond.cleanup22:
  %indvars.iv.next65 = add nuw nsw i64 %indvars.iv64, 1
  %exitcond67.not = icmp eq i64 %indvars.iv.next65, 64
  br i1 %exitcond67.not, label %for.cond.cleanup17, label %for.cond20.preheader

for.body23:
  %indvars.iv60 = phi i64 [ 0, %for.cond20.preheader ], [ %indvars.iv.next61, %for.body23 ]
  %arrayidx27 = getelementptr inbounds nuw [4 x i8], ptr %arrayidx25, i64 %indvars.iv60
  %1 = load float, ptr %arrayidx27, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx31 = getelementptr inbounds nuw [4 x i8], ptr %arrayidx29, i64 %indvars.iv60
  store float %add, ptr %arrayidx31, align 4
  %indvars.iv.next61 = add nuw nsw i64 %indvars.iv60, 1
  %exitcond63.not = icmp eq i64 %indvars.iv.next61, 64
  br i1 %exitcond63.not, label %for.cond.cleanup22, label %for.body23
}

; CHECK-NOT: Offset-aware fusion
; CHECK:     // 1st level tiling - Tiles
; CHECK:     Stmt_for_body4(32 * c0 + c2, 32 * c1 + c3);
; CHECK:     // 1st level tiling - Tiles
; CHECK:     Stmt_for_body23(32 * c0 + c2, 32 * c1 + c3);
; CHECK-NOT: Offset-aware fusion

; GREEDY-NOT:  Offset-aware fusion
; GREEDY:      for (int c0 = 0; c0 <= 63; c0 += 1)
; GREEDY-NEXT:   for (int c1 = 0; c1 <= 63; c1 += 1) {
; GREEDY-NEXT:     Stmt_for_body4(c0, c1);
; GREEDY-NEXT:     Stmt_for_body23(c0, c1);
; GREEDY-NEXT:   }
