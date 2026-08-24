import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";

/**
 * Issue #515 — the closed mobile drawer must not hold keyboard focus off-screen.
 *
 * The fix is `inert` on the `<aside>` while it is a *closed drawer*. Two things make this worth
 * a test rather than trusting the JSX: React 18 silently drops some unknown boolean attributes
 * (so the attribute may simply never reach the DOM), and the desktop sidebar is the SAME element
 * with the same `menuOpen === false` — inerting it there would make the whole nav unusable.
 */

function mockViewport(isDrawer: boolean) {
  const listeners = new Set<() => void>();
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: isDrawer,
      media: query,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
      onchange: null
    }))
  );
}

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin"
}));

describe("AppShell 모바일 드로어 (#515)", () => {
  beforeEach(() => {
    mockViewport(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("좁은 화면에서 닫힌 드로어는 inert라 탭 순서에서 빠진다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    const sidebar = document.getElementById("app-sidebar");
    expect(sidebar).not.toBeNull();
    // React must actually emit the attribute — a dropped attribute would silently reinstate
    // the bug while every other assertion still passed.
    expect(sidebar?.hasAttribute("inert"), "닫힌 드로어에 inert 속성이 있어야 한다").toBe(true);
  });

  it("드로어를 열면 inert가 해제된다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    expect(document.getElementById("app-sidebar")?.hasAttribute("inert")).toBe(false);
  });

  it("데스크톱 사이드바는 절대 inert가 아니다", () => {
    mockViewport(false);
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    // Same element, same menuOpen === false — inerting here would kill the desktop nav.
    expect(document.getElementById("app-sidebar")?.hasAttribute("inert")).toBe(false);
  });
});
