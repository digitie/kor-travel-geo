import {
  Activity,
  Archive,
  BarChart3,
  Braces,
  Database,
  FileText,
  GitBranch,
  ListChecks,
  MapPinned,
  RotateCcw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  TerminalSquare
} from "lucide-react";
import Link from "next/link";

const debugLinks = [
  { href: "/debug/geocode", label: "Geocode", icon: Search },
  { href: "/debug/reverse", label: "Reverse", icon: MapPinned },
  { href: "/debug/normalize", label: "Normalize", icon: Braces },
  { href: "/debug/explain", label: "Explain", icon: TerminalSquare }
];

const adminLinks = [
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
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>kraddr-geo-ui</strong>
          <span>내부 운영 콘솔</span>
        </div>
        <NavGroup title="Debug" links={debugLinks} />
        <NavGroup title="Admin" links={adminLinks} />
        <div className="nav-group">
          <p className="nav-title">Runtime</p>
          <Link className="nav-link" href="/admin/cache">
            <Activity size={17} />
            Metrics
          </Link>
          <Link className="nav-link" href="/admin/load">
            <RotateCcw size={17} />
            MV refresh
          </Link>
          <Link className="nav-link" href="/admin/tables">
            <Server size={17} />
            PostGIS
          </Link>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
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
          <Link className="nav-link" href={link.href} key={link.href}>
            <Icon size={17} />
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
