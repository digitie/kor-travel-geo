"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ADMIN_NAV_GROUPS, ADMIN_PAGES } from "@/lib/admin-pages";

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

/**
 * 최신 map admin의 header band를 geo의 기존 페이지 계약에 맞춘 공통 헤더.
 * 페이지별 라우트/API 흐름은 유지하고, section → title/actions → meta → description 순서를
 * 모든 화면에서 동일하게 만든다.
 */
export function PageHeader({ title, description, actions, section, meta }: PageHeaderProps) {
  const pathname = usePathname() ?? "";
  const sectionLabel = section ?? sectionForPath(pathname);

  return (
    <header className="page-head" data-slot="admin-shell-header">
      <div className="page-head-inner">
        {sectionLabel ? <p className="page-section">{sectionLabel}</p> : null}
        <div className="page-head-row">
          <div className="page-title">
            <h1>{title}</h1>
          </div>
          {actions ? <div className="page-actions">{actions}</div> : null}
        </div>
        {meta ? <div className="page-meta">{meta}</div> : null}
        {description ? <p className="page-description">{description}</p> : null}
      </div>
    </header>
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
