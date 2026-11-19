"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentPropsWithRef, MouseEvent, ReactNode } from "react";

export function DocumentNavLink({
  children,
  className,
  href,
  ariaLabel,
  onNavigate,
  title,
  markCurrent = true,
  ...anchorProps
}: Omit<ComponentPropsWithRef<"a">, "href"> & {
  ariaLabel?: string;
  children: ReactNode;
  className?: string;
  href: string;
  onNavigate?: () => void;
  title?: string;
  /** false면 현재 경로여도 aria-current를 달지 않는다(브랜드 링크 등 메뉴가 아닌 링크). */
  markCurrent?: boolean;
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
      {...anchorProps}
      aria-current={markCurrent && active ? "page" : undefined}
      aria-label={ariaLabel}
      className={className}
      href={href}
      prefetch={false}
      title={title}
      onClick={navigate}
    >
      {children}
    </Link>
  );
}
