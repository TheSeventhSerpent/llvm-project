; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
;
; Three loops over the same range are fused without a shift, under a single
; offset-aware fusion mark.
;
; void three(int n, float *restrict A, float *restrict B, float *restrict C,
;            float *restrict D) {
;   for (int i = 0; i < n; i++) B[i] = A[i] * 2;
;   for (int i = 0; i < n; i++) C[i] = B[i] + 1;
;   for (int i = 0; i < n; i++) D[i] = C[i] - B[i];
; }

define void @three(i32 %n, ptr %A, ptr %B, ptr %C, ptr %D) {
entry:
  %cmp44 = icmp sgt i32 %n, 0
  br i1 %cmp44, label %for.body.preheader, label %for.cond.cleanup18

for.body.preheader:
  %wide.trip.count = zext nneg i32 %n to i64
  br label %for.body

for.body7.preheader:
  %wide.trip.count54 = zext nneg i32 %n to i64
  br label %for.body7

for.body:
  %indvars.iv = phi i64 [ 0, %for.body.preheader ], [ %indvars.iv.next, %for.body ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %indvars.iv
  %0 = load float, ptr %arrayidx, align 4
  %mul = fmul float %0, 2.000000e+00
  %arrayidx2 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %indvars.iv
  store float %mul, ptr %arrayidx2, align 4
  %indvars.iv.next = add nuw nsw i64 %indvars.iv, 1
  %exitcond.not = icmp eq i64 %indvars.iv.next, %wide.trip.count
  br i1 %exitcond.not, label %for.body7.preheader, label %for.body

for.body19.preheader:
  %wide.trip.count59 = zext nneg i32 %n to i64
  br label %for.body19

for.body7:
  %indvars.iv51 = phi i64 [ 0, %for.body7.preheader ], [ %indvars.iv.next52, %for.body7 ]
  %arrayidx9 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %indvars.iv51
  %1 = load float, ptr %arrayidx9, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx11 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %indvars.iv51
  store float %add, ptr %arrayidx11, align 4
  %indvars.iv.next52 = add nuw nsw i64 %indvars.iv51, 1
  %exitcond55.not = icmp eq i64 %indvars.iv.next52, %wide.trip.count54
  br i1 %exitcond55.not, label %for.body19.preheader, label %for.body7

for.cond.cleanup18:
  ret void

for.body19:
  %indvars.iv56 = phi i64 [ 0, %for.body19.preheader ], [ %indvars.iv.next57, %for.body19 ]
  %arrayidx21 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %indvars.iv56
  %2 = load float, ptr %arrayidx21, align 4
  %arrayidx23 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %indvars.iv56
  %3 = load float, ptr %arrayidx23, align 4
  %sub = fsub float %2, %3
  %arrayidx25 = getelementptr inbounds nuw [4 x i8], ptr %D, i64 %indvars.iv56
  store float %sub, ptr %arrayidx25, align 4
  %indvars.iv.next57 = add nuw nsw i64 %indvars.iv56, 1
  %exitcond60.not = icmp eq i64 %indvars.iv.next57, %wide.trip.count59
  br i1 %exitcond60.not, label %for.cond.cleanup18, label %for.body19
}

; CHECK:      Calculated schedule:
; CHECK-NEXT: domain: "[n] -> { Stmt_for_body7[i0] : 0 <= i0 < n; Stmt_for_body[i0] : 0 <= i0 < n; Stmt_for_body19[i0] : 0 <= i0 < n }"
; CHECK-NEXT: child:
; CHECK-NEXT:   mark: "Offset-aware fusion"
; CHECK-NEXT:   child:
; CHECK-NEXT:     schedule: "[n] -> [{ Stmt_for_body19[i0] -> [(i0)]; Stmt_for_body7[i0] -> [(i0)]; Stmt_for_body[i0] -> [(i0)] }]"
; CHECK-NEXT:     child:
; CHECK-NEXT:       sequence:
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body[i0] }"
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body7[i0] }"
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body19[i0] }"
; CHECK-NOT:  mark: "Offset-aware fusion"
