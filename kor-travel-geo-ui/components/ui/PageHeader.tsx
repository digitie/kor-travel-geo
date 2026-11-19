"use client";

import type { ReactNode } from "react";
import { AdminPageTitle } from "@kor-travel/ui/admin-shell";
import { GEO_ADMIN_AREA } from "@/lib/admin-pages";

type PageHeaderProps = {
  title: string;
  /** 선택 — 상단 바 제목 옆에 작게 말줄임해 보이는 한 줄. */
  description?: string;
  /** 상단 바 오른쪽 동작. 모바일에서는 아이콘 버튼 1~2개로 둔다. */
  actions?: ReactNode;
};

/**
 * 페이지 제목을 AdminShell 상단 바(h1 "지오 - 페이지")로 보낸다. 본문에는 아무것도 그리지 않는다.
 * 페이지 제목·설명의 정본은 lib/admin-pages.ts다.
 */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return <AdminPageTitle actions={actions} area={GEO_ADMIN_AREA} description={description} title={title} />;
}
