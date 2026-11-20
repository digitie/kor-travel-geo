"use client";
// rail·모바일 drawer·상단 바는 Common AdminShell을 사용한다. Geo 경로·문서 이동·인증은 유지한다.

import {
  Archive,
  BarChart3,
  Braces,
  Database,
  FileText,
  Files,
  FolderUp,
  LayoutDashboard,
  ListChecks,
  LogOut,
  MapPinned,
  Search,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Workflow
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useRef, useState, type ReactNode } from "react";
import { AppMenu, type AppMenuLinkProps } from "@kor-travel/ui/app-menu";
import { AdminShell } from "@kor-travel/ui/admin-shell";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import {
  ADMIN_NAV_GROUPS,
  ADMIN_PAGES,
  DEBUG_PAGES,
  GEO_ADMIN_AREA,
  pageMetaForPath,
  type AdminPageKey
} from "@/lib/admin-pages";
import { cn } from "@/lib/utils";

const adminIcons: Record<AdminPageKey, typeof Search> = {
  home: LayoutDashboard,
  sourceFiles: FolderUp,
  files: Files,
  consistency: ListChecks,
  backups: Archive,
  dagster: Workflow,
  ops: ShieldCheck,
  logs: FileText,
  tables: Database,
  cache: BarChart3,
  settings: Settings,
  load: FolderUp
};

type NavItem = { href: string; label: string; icon: typeof Search };
type NavGroup = { group: string | null; items: NavItem[] };

/** 메뉴 그룹의 단일 정본. map처럼 개요(라벨 없는 root)가 먼저 오고, 기능 그룹이 뒤따른다. */
const NAV_GROUPS: NavGroup[] = [
  {
    group: null,
    items: [{ href: ADMIN_PAGES.home.path, label: ADMIN_PAGES.home.title, icon: LayoutDashboard }]
  },
  {
    group: "조회·진단",
    items: [
      { href: DEBUG_PAGES.geocode.path, label: DEBUG_PAGES.geocode.title, icon: Search },
      { href: DEBUG_PAGES.reverse.path, label: DEBUG_PAGES.reverse.title, icon: MapPinned },
      { href: DEBUG_PAGES.normalize.path, label: DEBUG_PAGES.normalize.title, icon: Braces },
      { href: DEBUG_PAGES.explain.path, label: DEBUG_PAGES.explain.title, icon: TerminalSquare }
    ]
  },
  ...ADMIN_NAV_GROUPS.map((group) => ({
    group: group.title,
    items: group.keys.map((key) => ({
      href: ADMIN_PAGES[key].path,
      label: ADMIN_PAGES[key].title,
      icon: adminIcons[key]
    }))
  }))
];

const COMMON_MENU_GROUPS = NAV_GROUPS.map((group) => ({
  id: group.group ?? "root",
  label: group.group ?? undefined,
  items: group.items.map(({ href, label, icon: Icon }) => ({
    id: href,
    href,
    label,
    exact: href === ADMIN_PAGES.home.path,
    icon: <Icon aria-hidden="true" className="size-4" />
  }))
}));

const navHrefs = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href));

const SIDEBAR_COLLAPSED_KEY = "kor-travel-geo:sidebar-collapsed";
const MAIN_CONTENT_ID = "main-content";

function isActive(pathname: string, href: string) {
  if (href === ADMIN_PAGES.home.path) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Rail nav row / footer row 레시피(map design.md §Macrostructure N3 · M9).
 * flat row · 30px · 500 · hover surface-subtle · active surface-muted.
 */
const railRowClass =
  "relative flex h-control-sm shrink-0 items-center gap-2.5 rounded-control px-3 text-xs font-medium whitespace-nowrap text-text-secondary transition-[color,background-color] duration-fast ease-out hover:bg-surface-subtle hover:text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:bg-surface-muted";

const railRowCollapsedClass = "lg:size-control lg:justify-center lg:gap-0 lg:px-0";

/** 전체 문서 이동(geo는 RSC 소프트 이동 대신 문서 이동을 쓴다 — navigation.spec). */
function GeoMenuLink({ children, className, ...props }: AppMenuLinkProps) {
  return (
    <DocumentNavLink
      {...props}
      ariaLabel={props["aria-label"]}
      className={className}
      title={props["aria-label"]}
    >
      {children}
    </DocumentNavLink>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  // 가장 긴 경로 일치로 서버 첫 렌더 제목과 현재 메뉴를 함께 정한다.
  const activeHref = navHrefs
    .filter((href) => isActive(pathname, href))
    .reduce<string | undefined>((best, href) => (!best || href.length > best.length ? href : best), undefined);
  // 서버 첫 렌더에도 상단 바가 "지오 - 페이지"와 페이지 설명을 갖도록 정본(lib/admin-pages.ts)에서 정한다.
  // 메뉴 밖 경로(/admin/load 등)도 포함한다. 각 page의 PageHeader가 같은 값으로 덮어쓴다.
  const pageMeta = pageMetaForPath(pathname);

  // 로그인 화면과 인증 처리에는 셸을 추가하지 않는다.
  if (pathname === "/login") return <>{children}</>;

  return (
    <AdminShell
      area={GEO_ADMIN_AREA}
      title={pageMeta?.title}
      description={pageMeta?.description}
      navigationKey={pathname}
      collapsedStorageKey={SIDEBAR_COLLAPSED_KEY}
      mainId={MAIN_CONTENT_ID}
      mainClassName="px-4 pt-4 pb-6 sm:px-6"
      labels={{
        menu: "주요 메뉴",
        collapseRail: "좌측 메뉴 접기",
        expandRail: "좌측 메뉴 펼치기"
      }}
      // 서비스 표시는 영역 이름만 둔다 — 앱 설명 문구("Admin UI")는 두지 않는다.
      brand={() => (
        <DocumentNavLink
          ariaLabel={`${GEO_ADMIN_AREA} 관리 홈`}
          href={ADMIN_PAGES.home.path}
          markCurrent={false}
          className="inline-flex min-w-0 items-center rounded-control px-1 text-sm font-semibold tracking-tight text-text-primary no-underline"
        >
          {GEO_ADMIN_AREA}
        </DocumentNavLink>
      )}
      menu={
        <AppMenu
          groups={COMMON_MENU_GROUPS}
          activeItemId={activeHref ?? null}
          pathname={pathname}
          label="주요 메뉴"
          linkComponent={GeoMenuLink}
          testId="geo-common-menu"
        />
      }
      railFooter={({ collapsed }) => <ButtonLogout collapsed={collapsed} />}
    >
      {children}
    </AdminShell>
  );
}

function ButtonLogout({
  collapsed = false,
  iconOnly = false,
  className
}: {
  /** lg rail 접힘 — 라벨을 lg 에서만 숨긴다. */
  collapsed?: boolean;
  /** 모든 breakpoint 에서 아이콘만(<lg 상단 행). */
  iconOnly?: boolean;
  className?: string;
}) {
  const labelHidden = iconOnly || collapsed;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function logout() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        signal: AbortSignal.timeout(5000)
      });
      if (!response.ok) throw new Error("logout failed");
      // 인증 컨텍스트와 클라이언트 캐시를 폐기하려 전체 문서를 새로 연다.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    } catch {
      setError("로그아웃하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        aria-busy={busy}
        aria-disabled={busy}
        aria-label={labelHidden ? "로그아웃" : undefined}
        className={cn(
          railRowClass,
          iconOnly ? "size-control-sm justify-center gap-0 px-0" : "w-full",
          !iconOnly && collapsed && railRowCollapsedClass,
          className
        )}
        title={labelHidden ? "로그아웃" : undefined}
        type="button"
        onClick={() => void logout()}
      >
        <LogOut aria-hidden="true" className="size-4 shrink-0 text-icon-default" />
        <span className={cn(iconOnly ? "sr-only" : collapsed && "lg:hidden")}>로그아웃</span>
      </button>
      {error ? (
        <p role="alert" className="px-2 text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
