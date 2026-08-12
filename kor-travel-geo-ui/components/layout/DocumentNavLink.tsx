"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { MouseEvent, ReactNode } from "react";

export function DocumentNavLink({
  children,
  className,
  href,
  onNavigate
}: {
  children: ReactNode;
  className?: string;
  href: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname() ?? "";
  const active =
    href === "/admin"
      ? pathname === href
      : pathname === href || pathname.startsWith(`${href}/`);

  function navigate(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey
    ) {
      return;
    }

    event.preventDefault();
    onNavigate?.();
    window.location.assign(href);
  }

  return (
    <Link
      aria-current={active ? "page" : undefined}
      className={className}
      href={href}
      prefetch={false}
      onClick={navigate}
    >
      {children}
    </Link>
  );
}
