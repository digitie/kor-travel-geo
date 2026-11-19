"use client";
// 관리자 셸은 @kor-travel/ui 0.2.3 `AdminShell`이 정본이다(common ADR-021). lg(1024px) 이상은 좌측
// rail(16rem, 접힘 4rem), 그 아래는 한 줄 상단 바의 메뉴 버튼으로 여는 좌측 drawer다. 페이지 제목은
// 상단 바 h1 "지오 - 페이지" 한 줄이고 페이지 설명은 같은 줄에 작게 둔다. 앱 설명 문구는 두지 않는다.

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
import { AdminShell } from "@kor-travel/ui/admin-shell";
import { AppMenu, type AppMenuLinkProps } from "@kor-travel/ui/app-menu";
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

/** 메뉴 그룹의 단일 정본. 개요(라벨 없는 root)가 먼저 오고, 기능 그룹이 뒤따른다. */
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

/** 기존 rail 접힘 저장값("1"/"0")은 그대로 읽고 같은 형식으로 쓴다. 저장값이 없으면 "true"/"false"로 쓴다(AdminShell). */
const SIDEBAR_COLLAPSED_KEY = "kor-travel-geo:sidebar-collapsed";

const SHELL_LABELS = {
  collapseRail: "좌측 메뉴 접기",
  expandRail: "좌측 메뉴 펼치기"
};

function isActive(pathname: string, href: string) {
  if (href === ADMIN_PAGES.home.path) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Rail footer row 레시피: flat row · 30px · 500 · hover surface-subtle · active surface-muted. */
const railRowClass =
  "relative flex h-control-sm shrink-0 items-center gap-2.5 rounded-control px-3 text-xs font-medium whitespace-nowrap text-text-secondary transition-[color,background-color] duration-fast ease-out hover:bg-surface-subtle hover:text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:bg-surface-muted";

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

function GeoBrand() {
  return (
    <DocumentNavLink
      ariaLabel={`${GEO_ADMIN_AREA} 관리 홈`}
      markCurrent={false}
      className="inline-flex min-w-0 items-center rounded-control px-1 text-sm font-semibold tracking-tight text-text-primary no-underline hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      href={ADMIN_PAGES.home.path}
    >
      {GEO_ADMIN_AREA}
    </DocumentNavLink>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  // longest-prefix 일치(예: /admin/consistency/123 → /admin/consistency, /admin 아님).
  const activeHref = navHrefs
    .filter((href) => isActive(pathname, href))
    .reduce<string | undefined>((best, href) => (!best || href.length > best.length ? href : best), undefined);

  // 로그인 화면은 shell 없이 단독으로 렌더된다(LoginForm이 <main>을 가진다).
  if (pathname === "/login") return <>{children}</>;

  // 서버 렌더 첫 화면에도 상단 바 제목이 있도록 nav 정본에서 제목·설명을 준다. 각 page의
  // PageHeader(AdminPageTitle)가 같은 값으로 덮어쓴다.
  const pageMeta = pageMetaForPath(pathname);

  return (
    <AdminShell
      area={GEO_ADMIN_AREA}
      brand={() => <GeoBrand />}
      collapsedStorageKey={SIDEBAR_COLLAPSED_KEY}
      description={pageMeta?.description}
      labels={SHELL_LABELS}
      mainClassName="px-4 pt-4 pb-6 sm:px-6 sm:pt-6"
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
      navigationKey={pathname}
      railFooter={({ collapsed }) => <ButtonLogout collapsed={collapsed} />}
      testId="geo-admin-shell"
      title={pageMeta?.title}
    >
      {children}
    </AdminShell>
  );
}

function ButtonLogout({ collapsed = false }: { /** 데스크톱 rail 접힘 — 라벨을 숨긴다. */ collapsed?: boolean }) {
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
        aria-label={collapsed ? "로그아웃" : undefined}
        className={cn(railRowClass, collapsed ? "mx-auto size-control justify-center gap-0 px-0" : "w-full")}
        title={collapsed ? "로그아웃" : undefined}
        type="button"
        onClick={() => void logout()}
      >
        <LogOut aria-hidden="true" className="size-4 shrink-0 text-icon-default" />
        <span className={cn(collapsed && "sr-only")}>로그아웃</span>
      </button>
      {error ? (
        <p role="alert" className="px-2 text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
