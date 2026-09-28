; RUN: opt %loadNPMPolly -polly-force-offset-fusion '-passes=polly-custom<scops>' -polly-print-scops -disable-output < %s | FileCheck %s
; RUN: opt %loadNPMPolly '-passes=polly-custom<scops>' -polly-print-scops -disable-output < %s | FileCheck %s --check-prefix=OFF
;
; Check the logical offsets recovered for offset-aware fusion.
;
; float f(long n, long m, float *restrict A, float *restrict B, float *restrict C,
;         float *restrict D, float *restrict E, float *restrict F) {
;   for (long i = 0; i < n; i++)     B[i] = A[i] * 2;
;   for (long i = 1; i < n; i++)     C[i] = B[i] + 1;
;   for (long i = 0; i < n - 1; i++) { D[i] = C[i] * 3; E[i + 1] = C[i] + 2; }
;   for (long i = 0; i < n; i++)     F[i + m] = A[i] - 1;
;   float s = 0;
;   for (long i = 0; i < n - 2; i++) s += A[i + 2];
;   return s;
; }

define float @f(i64 %n, i64 %m, ptr %A, ptr %B, ptr %C, ptr %D, ptr %E, ptr %F) {
entry:
  %cmp77 = icmp sgt i64 %n, 0
  br i1 %cmp77, label %for.body, label %for.cond.cleanup43

for.cond3.preheader:
  %cmp479.not = icmp eq i64 %n, 1
  br i1 %cmp479.not, label %for.body31.preheader, label %for.body6

for.body:
  %i.078 = phi i64 [ %inc, %for.body ], [ 0, %entry ]
  %arrayidx = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i.078
  %0 = load float, ptr %arrayidx, align 4
  %mul = fmul float %0, 2.000000e+00
  %arrayidx1 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i.078
  store float %mul, ptr %arrayidx1, align 4
  %inc = add nuw nsw i64 %i.078, 1
  %exitcond.not = icmp eq i64 %inc, %n
  br i1 %exitcond.not, label %for.cond3.preheader, label %for.body

for.body16.preheader:
  %1 = add nsw i64 %n, -2
  br label %for.body16

for.body6:
  %i2.080 = phi i64 [ %inc10, %for.body6 ], [ 1, %for.cond3.preheader ]
  %arrayidx7 = getelementptr inbounds nuw [4 x i8], ptr %B, i64 %i2.080
  %2 = load float, ptr %arrayidx7, align 4
  %add = fadd float %2, 1.000000e+00
  %arrayidx8 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i2.080
  store float %add, ptr %arrayidx8, align 4
  %inc10 = add nuw nsw i64 %i2.080, 1
  %exitcond88.not = icmp eq i64 %inc10, %n
  br i1 %exitcond88.not, label %for.body16.preheader, label %for.body6

for.body31.preheader:
  %invariant.gep98 = getelementptr [4 x i8], ptr %F, i64 %m
  br label %for.body31

for.body16:
  %i12.082 = phi i64 [ %add22, %for.body16 ], [ 0, %for.body16.preheader ]
  %arrayidx17 = getelementptr inbounds nuw [4 x i8], ptr %C, i64 %i12.082
  %3 = load float, ptr %arrayidx17, align 4
  %mul18 = fmul float %3, 3.000000e+00
  %arrayidx19 = getelementptr inbounds nuw [4 x i8], ptr %D, i64 %i12.082
  store float %mul18, ptr %arrayidx19, align 4
  %add21 = fadd float %3, 2.000000e+00
  %add22 = add nuw nsw i64 %i12.082, 1
  %arrayidx23 = getelementptr inbounds nuw [4 x i8], ptr %E, i64 %add22
  store float %add21, ptr %arrayidx23, align 4
  %exitcond89.not = icmp eq i64 %i12.082, %1
  br i1 %exitcond89.not, label %for.body31.preheader, label %for.body16

for.cond40.preheader:
  %cmp4285 = icmp samesign ugt i64 %n, 2
  br i1 %cmp4285, label %for.body44.preheader, label %for.cond.cleanup43

for.body44.preheader:
  %4 = add nsw i64 %n, -3
  br label %for.body44

for.body31:
  %i27.084 = phi i64 [ %inc37, %for.body31 ], [ 0, %for.body31.preheader ]
  %arrayidx32 = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i27.084
  %5 = load float, ptr %arrayidx32, align 4
  %sub33 = fadd float %5, -1.000000e+00
  %gep = getelementptr [4 x i8], ptr %invariant.gep98, i64 %i27.084
  store float %sub33, ptr %gep, align 4
  %inc37 = add nuw nsw i64 %i27.084, 1
  %exitcond90.not = icmp eq i64 %inc37, %n
  br i1 %exitcond90.not, label %for.cond40.preheader, label %for.body31

for.cond.cleanup43:
  %s.0.lcssa = phi float [ 0.000000e+00, %for.cond40.preheader ], [ 0.000000e+00, %entry ], [ %add47, %for.body44 ]
  ret float %s.0.lcssa

for.body44:
  %i39.087 = phi i64 [ %inc49, %for.body44 ], [ 0, %for.body44.preheader ]
  %s.086 = phi float [ %add47, %for.body44 ], [ 0.000000e+00, %for.body44.preheader ]
  %6 = getelementptr inbounds nuw [4 x i8], ptr %A, i64 %i39.087
  %arrayidx46 = getelementptr inbounds nuw i8, ptr %6, i64 8
  %7 = load float, ptr %arrayidx46, align 4
  %add47 = fadd float %s.086, %7
  %inc49 = add nuw nsw i64 %i39.087, 1
  %exitcond91.not = icmp eq i64 %i39.087, %4
  br i1 %exitcond91.not, label %for.cond.cleanup43, label %for.body44
}

; [0, n): offset 0.
; CHECK:      Stmt_for_body{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> { Stmt_for_body[i0] : 0 <= i0 < n };
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> { Stmt_for_body[i0] -> [0, i0] };
; CHECK-NEXT:   LogicalOffset := 0;
;
; [1, n): offset 1.
; CHECK:      Stmt_for_body6{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   LogicalOffset := 1;
;
; Writes D[i] and E[i + 1] disagree. The reads are not used as fallback.
; CHECK:      Stmt_for_body16{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   LogicalOffset := n/a;
;
; Parametric offset of the write F[i + m].
; CHECK:      Stmt_for_body31{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   LogicalOffset := n/a;
;
; Statements that are not one-dimensional have no offset.
; CHECK:      Stmt_for_cond40_preheader_last{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> {{.*}}
; CHECK-NEXT:   LogicalOffset := n/a;
;
; No array writes: the offset is taken from the read A[i + 2].
; CHECK:      Stmt_for_body44{{$}}
; CHECK-NEXT:   Domain :=
; CHECK-NEXT:     [n, m] -> { Stmt_for_body44[i0] : 0 <= i0 <= -3 + n };
; CHECK-NEXT:   Schedule :=
; CHECK-NEXT:     [n, m] -> { Stmt_for_body44[i0] -> [6, i0] };
; CHECK-NEXT:   LogicalOffset := 2;

; Without -polly-force-offset-fusion, nothing is printed.
; OFF:     Statements {
; OFF-NOT: LogicalOffset
