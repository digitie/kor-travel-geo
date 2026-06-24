"use client";

import Link from "next/link";
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
    <Link className={className} href={href} prefetch={false} onClick={navigate}>
      {children}
    </Link>
  );
}
