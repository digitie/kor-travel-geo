"use client";

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
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Workflow,
  X
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { ADMIN_NAV_GROUPS, ADMIN_PAGES, type AdminPageKey } from "@/lib/admin-pages";
import { useModalA11y } from "@/lib/use-modal-a11y";

const debugLinks = [
  { href: "/debug/geocode", label: "Geocode", icon: Search },
  { href: "/debug/reverse", label: "Reverse", icon: MapPinned },
  { href: "/debug/normalize", label: "Normalize", icon: Braces },
  { href: "/debug/explain", label: "Explain", icon: TerminalSquare }
];

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

// 사이드바 그룹: 조회·진단(디버그) + 관리 홈 + lib/admin-pages.ts의 기능 그룹.
// 같은 페이지를 다른 이름으로 다시 노출하던 Runtime 별칭 그룹은 제거했다.
const adminNavGroups = ADMIN_NAV_GROUPS.map((group) => ({
  title: group.title,
  links: group.keys.map((key) => ({
    href: ADMIN_PAGES[key].path,
    label: ADMIN_PAGES[key].title,
    icon: adminIcons[key]
  }))
}));

/** Matches the `@media (max-width: 1023px)` breakpoint where the sidebar becomes a drawer. */
export const DRAWER_MEDIA_QUERY = "(max-width: 1023px)";

const SIDEBAR_COLLAPSED_KEY = "kor-travel-geo:sidebar-collapsed";

/**
 * True while the sidebar is rendered as the off-canvas drawer.
 *
 * Needed because the closed drawer must be `inert` (out of the tab order and the a11y tree)
 * while the *desktop* sidebar — same element, same `menuOpen === false` — must stay fully
 * focusable. Starts `false` so SSR and the first client paint agree.
 */
function useIsDrawerLayout(): boolean {
  const [isDrawer, setIsDrawer] = useState(false);
  useEffect(() => {
    const query = window.matchMedia(DRAWER_MEDIA_QUERY);
    const sync = () => setIsDrawer(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return isDrawer;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const sidebarStateLoadedRef = useRef(false);
  const isDrawerLayout = useIsDrawerLayout();
  const pathname = usePathname();
  const sidebarRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    sidebarStateLoadedRef.current = true;
    if (stored === "1") setSidebarCollapsed(true);
  }, []);

  useEffect(() => {
    if (!sidebarStateLoadedRef.current) return;
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  // A closed drawer is only moved off-screen by a transform, so its links stayed in the tab
  // order and Tab sent focus somewhere invisible (issue #515). `inert` removes them from both
  // the tab order and the a11y tree. The CSS keeps a `visibility: hidden` baseline for the
  // window before this runs (see globals.css) — hydration, on every full page load.
  //
  // MUST be declared before useModalA11y: React flushes one commit's passive effects in hook
  // order, and focusing into an inert subtree is a silent no-op that un-inerting afterwards
  // does NOT replay. Registered the other way round, opening the drawer left focus stranded on
  // the hamburger (verified in Chromium and Firefox). tests/unit/app-shell-drawer.test.tsx
  // pins the ordering.
  //
  // Set imperatively: React 18 drops `inert={true}` on the way to the DOM (also covered by
  // that test), so a JSX prop would silently do nothing. Never applied to the desktop sidebar —
  // same element, same `menuOpen === false`, but not a drawer.
  useEffect(() => {
    sidebarRef.current?.toggleAttribute("inert", isDrawerLayout && !menuOpen);
  }, [isDrawerLayout, menuOpen]);

  // Growing past the drawer breakpoint while the drawer is open would strand the desktop
  // layout: body scroll stays locked and <main> stays aria-hidden, while every control that
  // could close it (top bar, close button, backdrop) is `display: none` outside the media
  // query — leaving no visible way out.
  //
  // Focus has to be re-homed too. On close, useModalA11y restores focus to the hamburger — but
  // at desktop width the hamburger is inside `.mobile-topbar { display: none }`, and the
  // `.sidebar-close` the user was probably on is hidden as well, so focus falls to <body> and
  // a keyboard user loses their place. Hand it to <main> instead.
  useEffect(() => {
    if (isDrawerLayout) return;
    if (!menuOpen) return;
    const focusInsideSidebar = sidebarRef.current?.contains(document.activeElement) ?? false;
    setMenuOpen(false);
    if (focusInsideSidebar) {
      // After the commit that unlocks <main> (it is aria-hidden while the drawer is open).
      queueMicrotask(() => mainRef.current?.focus());
    }
  }, [isDrawerLayout, menuOpen]);

  // On mobile the sidebar is an off-canvas modal drawer, so give it the same keyboard/AT
  // behavior as the admin dialogs: Escape closes it, focus moves in and is trapped while open,
  // and focus returns to the toggle on close. `open` is passed because the drawer is always
  // mounted and CSS-toggled (unlike the mount-on-open admin modals).
  useModalA11y({
    dialogRef: sidebarRef,
    onClose: closeMenu,
    initialFocusRef: closeButtonRef,
    open: menuOpen
  });

  // Lock background scroll while the drawer is open so touch scroll-chaining can't move the
  // page behind the backdrop.
  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  // The login page renders standalone (no shell chrome). Placed after all hooks so hook order
  // stays stable across routes (rules of hooks).
  if (pathname === "/login") {
    return <main className="login-content">{children}</main>;
  }

  return (
    <div
      className="app-shell"
      data-menu-open={menuOpen}
      data-sidebar-collapsed={sidebarCollapsed}
    >
      <a className="skip-link" href="#main-content">
        본문으로 건너뛰기
      </a>
      <header className="mobile-topbar">
        <button
          className="mobile-menu-toggle"
          type="button"
          aria-label={menuOpen ? "메뉴 닫기" : "메뉴 열기"}
          aria-expanded={menuOpen}
          aria-controls="app-sidebar"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <strong className="mobile-topbar-title">Geocoder Admin UI</strong>
      </header>
      <button
        className="sidebar-backdrop"
        type="button"
        aria-label="메뉴 닫기"
        tabIndex={menuOpen ? 0 : -1}
        onClick={closeMenu}
      />
      <aside
        id="app-sidebar"
        ref={sidebarRef}
        className="sidebar"
        role={menuOpen ? "dialog" : undefined}
        aria-modal={menuOpen ? true : undefined}
        aria-label={menuOpen ? "내비게이션 메뉴" : undefined}
        data-slot="admin-shell-rail"
      >
        <div className="rail-inner">
          <div className="rail-header">
            <Link
              aria-label="Geocoder Admin UI"
              className="rail-brand"
              href={ADMIN_PAGES.home.path}
            >
              <span className="rail-brand-name">Geocoder</span>
              <span className="rail-brand-suffix">Admin UI</span>
              <span aria-hidden="true" className="rail-brand-compact">
                GA
              </span>
            </Link>
            <div className="rail-actions">
              <button
                ref={closeButtonRef}
                className="sidebar-close"
                type="button"
                aria-label="메뉴 닫기"
                onClick={closeMenu}
              >
                <X size={18} />
              </button>
              <button
                aria-label={sidebarCollapsed ? "좌측 메뉴 펼치기" : "좌측 메뉴 접기"}
                className="sidebar-collapse"
                title={sidebarCollapsed ? "좌측 메뉴 펼치기" : "좌측 메뉴 접기"}
                type="button"
                onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
              >
                {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </button>
            </div>
          </div>
          <div className="rail-nav">
            <NavGroup
              collapsed={sidebarCollapsed}
              title="조회·진단"
              links={debugLinks}
              onNavigate={closeMenu}
            />
            <nav className="nav-group" aria-label="개요">
              <p className="nav-title">개요</p>
              <DocumentNavLink
                ariaLabel={sidebarCollapsed ? ADMIN_PAGES.home.title : undefined}
                className="nav-link"
                href={ADMIN_PAGES.home.path}
                onNavigate={closeMenu}
                title={sidebarCollapsed ? ADMIN_PAGES.home.title : undefined}
              >
                <LayoutDashboard size={17} />
                <span className="nav-label">{ADMIN_PAGES.home.title}</span>
              </DocumentNavLink>
            </nav>
            {adminNavGroups.map((group) => (
              <NavGroup
                collapsed={sidebarCollapsed}
                key={group.title}
                title={group.title}
                links={group.links}
                onNavigate={closeMenu}
              />
            ))}
          </div>
          <div className="sidebar-footer">
            <button
              aria-label={sidebarCollapsed ? "로그아웃" : undefined}
              className="nav-link nav-button"
              title={sidebarCollapsed ? "로그아웃" : undefined}
              type="button"
              onClick={() => void logout()}
            >
              <LogOut size={17} />
              <span className="nav-label">로그아웃</span>
            </button>
          </div>
        </div>
      </aside>
      <main
        className="content"
        aria-hidden={menuOpen || undefined}
        data-slot="admin-shell-main"
        id="main-content"
        ref={mainRef}
        tabIndex={-1}
      >
        {children}
      </main>
    </div>
  );
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/login");
  }
}

function NavGroup({
  collapsed,
  title,
  links,
  onNavigate
}: {
  collapsed: boolean;
  title: string;
  links: { href: string; label: string; icon: typeof Search }[];
  onNavigate: () => void;
}) {
  return (
    <nav className="nav-group" aria-label={title}>
      <p className="nav-title">{title}</p>
      {links.map((link) => {
        const Icon = link.icon;
        return (
          <DocumentNavLink
            ariaLabel={collapsed ? link.label : undefined}
            className="nav-link"
            href={link.href}
            key={link.href}
            onNavigate={onNavigate}
            title={collapsed ? link.label : undefined}
          >
            <Icon size={17} />
            <span className="nav-label">{link.label}</span>
          </DocumentNavLink>
        );
      })}
    </nav>
  );
}
