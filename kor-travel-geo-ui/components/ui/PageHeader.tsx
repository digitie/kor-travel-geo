"use client";

import { usePathname } from "next/navigation";
import { AdminPageTitle } from "@kor-travel/ui/admin-shell";
import type { ReactNode } from "react";
import { ADMIN_NAV_GROUPS, ADMIN_PAGES, GEO_ADMIN_AREA } from "@/lib/admin-pages";

type PageHeaderProps = {
  title: string;
  /** 선택 — 정말 필요한 한 줄만. 탭/패널 제목과 중복되면 생략한다. */
  description?: string;
  actions?: ReactNode;
  /** 생략하면 현재 경로의 관리자 메뉴 그룹에서 자동으로 정한다. */
  section?: string;
  /** 제목 아래 한 줄 메타(상태·갱신 시각·건수 등). */
  meta?: ReactNode;
};

/** 페이지의 제목·설명·동작은 Common 상단 바로 등록하고 상세 메타는 본문에 남긴다. */
export function PageHeader({ title, description, actions, section, meta }: PageHeaderProps) {
  const pathname = usePathname() ?? "";
  const sectionLabel = section ?? sectionForPath(pathname);

  return (
    <>
      <AdminPageTitle area={GEO_ADMIN_AREA} title={title} description={description} actions={actions} />
      {sectionLabel || meta ? (
        <div className="mb-4 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
          {sectionLabel ? <p className="text-2xs font-medium">{sectionLabel}</p> : null}
          {meta ? <div className="flex flex-wrap items-center gap-x-2 gap-y-1">{meta}</div> : null}
        </div>
      ) : null}
    </>
  );
}

function sectionForPath(pathname: string): string | undefined {
  if (pathname.startsWith("/debug/")) return "조회·진단";
  if (pathname === ADMIN_PAGES.home.path) return "개요";

  for (const group of ADMIN_NAV_GROUPS) {
    if (group.keys.some((key) => pathMatches(pathname, ADMIN_PAGES[key].path))) {
      return group.title;
    }
  }

  return pathname.startsWith("/admin/") ? "관리" : undefined;
}

function pathMatches(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
