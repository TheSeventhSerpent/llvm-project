; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly -polly-force-offset-fusion -polly-offset-fusion-isolate=0 '-passes=polly-custom<opt-isl;ast>' -polly-print-ast -disable-output < %s | FileCheck %s --check-prefix=NOISO
; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<opt-isl;ast;codegen>' -S < %s | FileCheck %s --check-prefix=CODEGEN
;
; After offset-aware fusion of loops over [0, n), [1, n) and [0, n - 1), all
; three loop bodies are executed in the iterations 1 <= c0 < n - 1. These are
; generated as a loop without conditions. The other iterations form a prologue
; and an epilogue.
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

; CHECK:      // Offset-aware fusion
; CHECK-NEXT: {
; CHECK-NEXT:   if (n >= 3) {
; CHECK-NEXT:     Stmt_for_body(0);
; CHECK-NEXT:     Stmt_for_body19(0);
; CHECK-NEXT:   }
; CHECK-NEXT:   for (int c0 = 1; c0 < n - 1; c0 += 1) {
; CHECK-NEXT:     Stmt_for_body(c0);
; CHECK-NEXT:     Stmt_for_body7(c0 - 1);
; CHECK-NEXT:     Stmt_for_body19(c0);
; CHECK-NEXT:   }
; CHECK-NEXT:   if (n >= 3) {
; CHECK-NEXT:     Stmt_for_body(n - 1);
; CHECK-NEXT:     Stmt_for_body7(n - 2);
; CHECK-NEXT:   } else {
; CHECK-NEXT:     for (int c0 = 0; c0 < n; c0 += 1) {
; CHECK-NEXT:       Stmt_for_body(c0);
; CHECK-NEXT:       if (n == 2 && c0 == 1) {
; CHECK-NEXT:         Stmt_for_body7(0);
; CHECK-NEXT:       } else if (n == 2) {
; CHECK-NEXT:         Stmt_for_body19(0);
; CHECK-NEXT:       }
; CHECK-NEXT:     }
; CHECK-NEXT:   }
; CHECK-NEXT: }

; NOISO:      // Offset-aware fusion
; NOISO-NEXT: for (int c0 = 0; c0 < n; c0 += 1) {
; NOISO-NEXT:   Stmt_for_body(c0);
; NOISO-NEXT:   if (c0 >= 1)
; NOISO-NEXT:     Stmt_for_body7(c0 - 1);
; NOISO-NEXT:   if (n >= c0 + 2)
; NOISO-NEXT:     Stmt_for_body19(c0);
; NOISO-NEXT: }

; CODEGEN: br i1 %polly.rtc.result, label %polly.start
; CODEGEN: polly.stmt.for.body:
