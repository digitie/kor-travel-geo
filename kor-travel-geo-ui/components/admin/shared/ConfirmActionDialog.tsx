"use client";

import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger
} from "@/components/ui/alert-dialog";
import { RoleRequirementNote } from "@/components/admin/RoleRequirementNote";

/**
 * 파괴적/되돌리기 어려운 액션의 표준 확인 다이얼로그.
 * 확인 없이 즉시 실행되던 버튼(artifact 삭제, job 취소, 키 폐기, 전체 재검증 등)을
 * 이 컴포넌트로 감싼다. typed confirmation이 필요한 흐름은 children으로
 * TypedConfirmField를 넣고 confirmDisabled로 게이트한다.
 */
export function ConfirmActionDialog({
  trigger,
  title,
  description,
  roles,
  confirmLabel = "실행",
  cancelLabel = "취소",
  destructive = true,
  confirmDisabled = false,
  onConfirm,
  onOpenChange,
  children
}: {
  /** 트리거 버튼 (asChild로 감싼다). */
  trigger: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  /** 표시할 필요 역할 (백엔드 require_role 안내). */
  roles?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void | Promise<void>;
  onOpenChange?: (open: boolean) => void;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description ? (
            <AlertDialogDescription>{description}</AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        {roles?.length ? <RoleRequirementNote roles={roles} /> : null}
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            variant={destructive ? "destructive" : "default"}
            disabled={confirmDisabled}
            onClick={() => void onConfirm()}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
