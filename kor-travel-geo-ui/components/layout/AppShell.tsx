"use client";

import {
  Activity,
  Archive,
  BarChart3,
  Braces,
  Database,
  FileText,
  FolderUp,
  GitBranch,
  ListChecks,
  LogOut,
  MapPinned,
  Menu,
  RotateCcw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  TerminalSquare,
  X
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";

const debugLinks = [
  { href: "/debug/geocode", label: "Geocode", icon: Search },
  { href: "/debug/reverse", label: "Reverse", icon: MapPinned },
  { href: "/debug/normalize", label: "Normalize", icon: Braces },
  { href: "/debug/explain", label: "Explain", icon: TerminalSquare }
];

const adminLinks = [
  { href: "/admin/source-files", label: "Source Files", icon: FolderUp },
  { href: "/admin/load", label: "Load", icon: GitBranch },
  { href: "/admin/backups", label: "Backups", icon: Archive },
  { href: "/admin/tables", label: "Tables", icon: Database },
  { href: "/admin/cache", label: "Cache", icon: BarChart3 },
  { href: "/admin/logs", label: "Logs", icon: FileText },
  { href: "/admin/consistency", label: "Consistency", icon: ListChecks },
  { href: "/admin/ops", label: "Ops", icon: ShieldCheck },
  { href: "/admin/settings", label: "Settings", icon: Settings }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();

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
        onClick={() => setMenuOpen(false)}
      />
      <aside id="app-sidebar" className="sidebar" onClick={() => setMenuOpen(false)}>
        <div className="brand">
          <strong>kor-travel-geo-ui</strong>
          <span>내부 운영 콘솔</span>
        </div>
        <NavGroup title="Debug" links={debugLinks} />
        <NavGroup title="Admin" links={adminLinks} />
        <div className="nav-group">
          <p className="nav-title">Runtime</p>
          <DocumentNavLink className="nav-link" href="/admin/cache">
            <Activity size={17} />
            Metrics
          </DocumentNavLink>
          <DocumentNavLink className="nav-link" href="/admin/load">
            <RotateCcw size={17} />
            MV refresh
          </DocumentNavLink>
          <DocumentNavLink className="nav-link" href="/admin/tables">
            <Server size={17} />
            PostGIS
          </DocumentNavLink>
        </div>
        <div className="sidebar-footer">
          <button className="nav-link nav-button" type="button" onClick={() => void logout()}>
            <LogOut size={17} />
            로그아웃
          </button>
        </div>
      </aside>
      <main className="content">{children}</main>
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
  links
}: {
  title: string;
  links: { href: string; label: string; icon: typeof Search }[];
}) {
  return (
    <nav className="nav-group" aria-label={title}>
      <p className="nav-title">{title}</p>
      {links.map((link) => {
        const Icon = link.icon;
        return (
          <DocumentNavLink className="nav-link" href={link.href} key={link.href}>
            <Icon size={17} />
            {link.label}
          </DocumentNavLink>
        );
      })}
    </nav>
  );
}
