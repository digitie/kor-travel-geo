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
  Search,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Workflow,
  X
} from "lucide-react";
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

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const sidebarRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

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
    <div className="app-shell" data-menu-open={menuOpen}>
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
        <strong className="mobile-topbar-title">kor-travel-geo-ui</strong>
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
      >
        <button
          ref={closeButtonRef}
          className="sidebar-close"
          type="button"
          aria-label="메뉴 닫기"
          onClick={closeMenu}
        >
          <X size={18} />
        </button>
        <div className="brand">
          <strong>kor-travel-geo-ui</strong>
          <span>내부 운영 콘솔</span>
        </div>
        <NavGroup title="조회·진단" links={debugLinks} onNavigate={closeMenu} />
        <nav className="nav-group" aria-label="관리 홈">
          <p className="nav-title">관리</p>
          <DocumentNavLink
            className="nav-link"
            href={ADMIN_PAGES.home.path}
            onNavigate={closeMenu}
          >
            <LayoutDashboard size={17} />
            {ADMIN_PAGES.home.title}
          </DocumentNavLink>
        </nav>
        {adminNavGroups.map((group) => (
          <NavGroup
            key={group.title}
            title={group.title}
            links={group.links}
            onNavigate={closeMenu}
          />
        ))}
        <div className="sidebar-footer">
          <button className="nav-link nav-button" type="button" onClick={() => void logout()}>
            <LogOut size={17} />
            로그아웃
          </button>
        </div>
      </aside>
      <main className="content" aria-hidden={menuOpen || undefined}>
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
  title,
  links,
  onNavigate
}: {
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
            className="nav-link"
            href={link.href}
            key={link.href}
            onNavigate={onNavigate}
          >
            <Icon size={17} />
            {link.label}
          </DocumentNavLink>
        );
      })}
    </nav>
  );
}
