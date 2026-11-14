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
    // map AdminShell의 flush header band: section → h1 + actions 한 baseline → meta → description, 아래 hairline.
    // <main>의 좌우 여백(px-6)을 음수 margin으로 상쇄해 hairline이 본문 폭 전체에 닿게 한다.
    <header
      className="-mx-6 mb-6 border-b border-border px-6 pt-5 pb-4"
      data-slot="admin-shell-header"
    >
      <div className="flex min-w-0 flex-col gap-1">
        {sectionLabel ? <p className="text-2xs font-medium text-text-secondary">{sectionLabel}</p> : null}
        <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-center md:justify-between md:gap-6">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="text-xl leading-tight font-bold tracking-tight text-text-primary">{title}</h1>
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        {meta ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-secondary">{meta}</div>
        ) : null}
        {description ? <p className="max-w-3xl text-xs text-text-secondary">{description}</p> : null}
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
