"use client";
// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · designed-as-app
// 최신 kor-travel-map admin `AdminShell`(packages/kor-travel-map-admin/frontend/src/components/admin-shell.tsx)의
// rail·워드마크·메뉴·로그아웃 구조를 그대로 옮겼다. 색은 geo의 blue 토큰을 그대로 쓴다.

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
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Workflow
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { AppMenu, type AppMenuLinkProps } from "@kor-travel/ui/app-menu";
import { buttonVariants } from "@kor-travel/ui/button-variants";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { ADMIN_NAV_GROUPS, ADMIN_PAGES, type AdminPageKey } from "@/lib/admin-pages";
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
      { href: "/debug/geocode", label: "Geocode", icon: Search },
      { href: "/debug/reverse", label: "Reverse", icon: MapPinned },
      { href: "/debug/normalize", label: "Normalize", icon: Braces },
      { href: "/debug/explain", label: "Explain", icon: TerminalSquare }
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

function subscribeSidebar(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("geo-sidebar-preference", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("geo-sidebar-preference", listener);
  };
}
const readSidebar = () => window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
const serverSidebar = () => false;

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
  const menuContainerRef = useRef<HTMLDivElement | null>(null);
  const sidebarCollapsed = useSyncExternalStore(subscribeSidebar, readSidebar, serverSidebar);
  // longest-prefix 일치(예: /admin/consistency/123 → /admin/consistency, /admin 아님).
  const activeHref = navHrefs
    .filter((href) => isActive(pathname, href))
    .reduce<string | undefined>((best, href) => (!best || href.length > best.length ? href : best), undefined);

  useEffect(() => {
    if (window.innerWidth >= 1024) return;
    // reduced-motion 이면 smooth scroll 대신 즉시 이동.
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    menuContainerRef.current?.querySelector("[aria-current=page]")?.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "nearest",
      inline: "center"
    });
  }, [activeHref]);

  // 로그인 화면은 shell 없이 단독으로 렌더된다(map과 동일 — LoginForm이 <main>을 가진다).
  if (pathname === "/login") return <>{children}</>;

  const toggleSidebar = () => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? "0" : "1");
    window.dispatchEvent(new Event("geo-sidebar-preference"));
  };

  return (
    <div className="min-h-dvh bg-surface-page text-text-primary">
      {/* skip link — rail 항목을 건너뛰어 <main> 으로. nav 밖. */}
      <a
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:border focus:border-border focus:bg-card focus:px-3 focus:py-2 focus:text-xs focus:font-medium focus:text-text-primary focus:shadow-elevated focus:outline-2 focus:outline-offset-2 focus:outline-focus"
        href={`#${MAIN_CONTENT_ID}`}
      >
        본문으로 건너뛰기
      </a>
      <div
        className={cn(
          // gap-0: geo의 레거시 `.grid:not([class*="gap-"])` 간격 규칙이 rail과 본문 사이에 틈을 넣지 않게 한다.
          "grid min-h-dvh min-w-0 gap-0",
          sidebarCollapsed ? "lg:grid-cols-[4rem_minmax(0,1fr)]" : "lg:grid-cols-[16rem_minmax(0,1fr)]"
        )}
        data-sidebar-collapsed={sidebarCollapsed}
      >
        {/* Rail: card 표면 위 hairline 분리, rest shadow 없음. lg 에서 sticky 전체 높이. */}
        <aside
          className="min-w-0 border-b border-border bg-card lg:sticky lg:top-0 lg:h-dvh lg:self-start lg:border-r lg:border-b-0"
          data-slot="admin-shell-rail"
        >
          <div className="flex h-full min-w-0 flex-col">
            <div
              className={cn(
                "flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-4",
                sidebarCollapsed && "lg:h-auto lg:flex-col lg:justify-center lg:gap-1 lg:px-0 lg:py-2"
              )}
            >
              {/* 타이포 워드마크 — 아이콘 타일 없음. 접힘 시 축약형 `GA`. */}
              <DocumentNavLink
                ariaLabel="Geocoder Admin UI"
                className={cn(
                  "flex min-w-0 items-baseline gap-1.5 rounded-control text-text-primary no-underline hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
                  sidebarCollapsed && "lg:justify-center"
                )}
                href={ADMIN_PAGES.home.path}
              >
                <span className={cn("truncate text-sm font-semibold tracking-tight", sidebarCollapsed && "lg:hidden")}>
                  Geocoder
                </span>
                <span className={cn("text-2xs font-medium text-text-tertiary", sidebarCollapsed && "lg:hidden")}>
                  Admin UI
                </span>
                <span
                  aria-hidden="true"
                  className={cn("hidden text-xs font-semibold tracking-tight", sidebarCollapsed && "lg:inline")}
                >
                  GA
                </span>
              </DocumentNavLink>
              <div className="flex shrink-0 items-center gap-1">
                <ButtonLogout className="lg:hidden" iconOnly />
                <button
                  aria-label={sidebarCollapsed ? "좌측 메뉴 펼치기" : "좌측 메뉴 접기"}
                  className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), "hidden lg:inline-flex")}
                  title={sidebarCollapsed ? "좌측 메뉴 펼치기" : "좌측 메뉴 접기"}
                  type="button"
                  onClick={toggleSidebar}
                >
                  {sidebarCollapsed ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
                </button>
              </div>
            </div>
            <div
              ref={menuContainerRef}
              data-collapsed={sidebarCollapsed}
              className="geo-common-menu geo-common-surface min-h-0 max-w-full overflow-x-auto px-2 py-2 lg:flex-1 lg:overflow-x-hidden lg:overflow-y-auto"
            >
              <AppMenu
                groups={COMMON_MENU_GROUPS}
                activeItemId={activeHref ?? null}
                pathname={pathname}
                label="주요 메뉴"
                linkComponent={GeoMenuLink}
                testId="geo-common-menu"
              />
            </div>
            {/* 로그아웃 = rail footer 의 plain row. <lg 에서는 상단 워드마크 행의 아이콘 버튼이 대신한다. */}
            <div
              className={cn(
                "hidden shrink-0 border-t border-border p-2 lg:block",
                sidebarCollapsed && "lg:flex lg:justify-center"
              )}
            >
              <ButtonLogout collapsed={sidebarCollapsed} />
            </div>
          </div>
        </aside>
        <div className="flex min-w-0 flex-col">
          {/* <main> 은 children 만 감싼다. skip link 대상. 헤더 밴드는 각 페이지의 PageHeader가 그린다. */}
          <main
            className="min-w-0 flex-1 px-6 pb-6 focus-visible:outline-0"
            data-slot="admin-shell-main"
            id={MAIN_CONTENT_ID}
            tabIndex={-1}
          >
            {children}
          </main>
        </div>
      </div>
    </div>
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
