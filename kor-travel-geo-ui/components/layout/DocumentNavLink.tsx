"use client";

import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

export function DocumentNavLink({
  children,
  className,
  href
}: {
  children: ReactNode;
  className?: string;
  href: string;
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
    window.location.assign(href);
  }

  return (
    <Link className={className} href={href} prefetch={false} onClick={navigate}>
      {children}
    </Link>
  );
}
