; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-shift=0 -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s --check-prefix=NOSHIFT
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-shift=0 -polly-reschedule=1 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s --check-prefix=NOSHIFT
; RUN: opt %loadNPMPolly -polly-reschedule=0 -polly-postopts=0 '-passes=polly-custom<opt-isl>' -polly-print-opt-isl -disable-output < %s | FileCheck %s --check-prefix=OFF
;
; Offset-aware fusion of loops over [0, n), [1, n) and [0, n - 1). The second
; loop is shifted by one iteration, which aligns all three loops by the element
; index they process. The third loop is then fused without a shift.
;
; void chain(int n, float *restrict A, float *restrict B, float *restrict C,
;            float *restrict D) {
;   for (int i = 0; i < n; i++)     B[i] = A[i] * 2;    // [0, n)
;   for (int i = 1; i < n; i++)     C[i] = B[i] + 1;    // [1, n)
;   for (int i = 0; i < n - 1; i++) D[i] = C[i] - B[i]; // [0, n - 1)
; }

define void @chain(i32 %n, ptr %A, ptr %B, ptr %C, ptr %D) {
entry:
  %cmp45 = icmp sgt i32 %n, 0
  br i1 %cmp45, label %for.body.preheader, label %for.cond.cleanup18

for.body.preheader:
  %wide.trip.count = zext nneg i32 %n to i64
  br label %for.body

for.cond4.preheader:
  %cmp547.not = icmp eq i32 %n, 1
  br i1 %cmp547.not, label %for.cond.cleanup18, label %for.body7.preheader

for.body7.preheader:
  %wide.trip.count55 = zext nneg i32 %n to i64
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
  br i1 %exitcond.not, label %for.cond4.preheader, label %for.body

for.body19.preheader:
  %sub = add nsw i32 %n, -1
  %wide.trip.count60 = zext nneg i32 %sub to i64
  br label %for.body19

for.body7:
  %indvars.iv52 = phi i64 [ 1, %for.body7.preheader ], [ %indvars.iv.next53, %for.body7 ]
  %arrayidx9 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %indvars.iv52
  %1 = load float, ptr %arrayidx9, align 4
  %add = fadd float %1, 1.000000e+00
  %arrayidx11 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %indvars.iv52
  store float %add, ptr %arrayidx11, align 4
  %indvars.iv.next53 = add nuw nsw i64 %indvars.iv52, 1
  %exitcond56.not = icmp eq i64 %indvars.iv.next53, %wide.trip.count55
  br i1 %exitcond56.not, label %for.body19.preheader, label %for.body7

for.cond.cleanup18:
  ret void

for.body19:
  %indvars.iv57 = phi i64 [ 0, %for.body19.preheader ], [ %indvars.iv.next58, %for.body19 ]
  %arrayidx21 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %indvars.iv57
  %2 = load float, ptr %arrayidx21, align 4
  %arrayidx23 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %indvars.iv57
  %3 = load float, ptr %arrayidx23, align 4
  %sub24 = fsub float %2, %3
  %arrayidx26 = getelementptr inbounds nuw [4 x i8], ptr %D, i64 %indvars.iv57
  store float %sub24, ptr %arrayidx26, align 4
  %indvars.iv.next58 = add nuw nsw i64 %indvars.iv57, 1
  %exitcond61.not = icmp eq i64 %indvars.iv.next58, %wide.trip.count60
  br i1 %exitcond61.not, label %for.cond.cleanup18, label %for.body19
}

; CHECK:      Calculated schedule:
; CHECK-NEXT: domain: "[n] -> { Stmt_for_body7[i0] : 0 <= i0 <= -2 + n; Stmt_for_body[i0] : 0 <= i0 < n; Stmt_for_body19[i0] : 0 <= i0 <= -2 + n }"
; CHECK-NEXT: child:
; CHECK-NEXT:   mark: "Offset-aware fusion"
; CHECK-NEXT:   child:
; CHECK-NEXT:     schedule: "[n] -> [{ Stmt_for_body19[i0] -> [(i0)]; Stmt_for_body7[i0] -> [(1 + i0)]; Stmt_for_body[i0] -> [(i0)] }]"
; CHECK-NEXT:     child:
; CHECK-NEXT:       sequence:
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body[i0] }"
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body7[i0] }"
; CHECK-NEXT:       - filter: "[n] -> { Stmt_for_body19[i0] }"

; Without shifts, only the last two loops can be fused.
; NOSHIFT:      Calculated schedule:
; NOSHIFT:        sequence:
; NOSHIFT-NEXT:   - filter: "[n] -> { Stmt_for_body[i0] }"
; NOSHIFT:        - filter: "[n] -> { Stmt_for_body19[i0]; Stmt_for_body7[i0] }"
; NOSHIFT-NEXT:     child:
; NOSHIFT-NEXT:       mark: "Offset-aware fusion"
; NOSHIFT-NEXT:       child:
; NOSHIFT-NEXT:         schedule: "[n] -> [{ Stmt_for_body19[i0] -> [(i0)]; Stmt_for_body7[i0] -> [(i0)] }]"
; NOSHIFT-NEXT:         child:
; NOSHIFT-NEXT:           sequence:
; NOSHIFT-NEXT:           - filter: "[n] -> { Stmt_for_body7[i0] }"
; NOSHIFT-NEXT:           - filter: "[n] -> { Stmt_for_body19[i0] }"

; Without -polly-force-offset-fusion, nothing is fused.
; OFF:      Calculated schedule:
; OFF-NEXT: n/a
