import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell, DRAWER_MEDIA_QUERY } from "@/components/layout/AppShell";

/**
 * Issue #515 — the closed mobile drawer must not hold keyboard focus off-screen.
 *
 * The fix is `inert` on the `<aside>` while it is a *closed drawer*. Several things make this
 * worth tests rather than trusting the JSX:
 *  - React 18 silently drops some unknown boolean attributes, so `inert` may never reach the DOM;
 *  - the desktop sidebar is the SAME element with the same `menuOpen === false`, and inerting it
 *    there would make the whole nav unusable;
 *  - focusing into an inert subtree is a no-op, so the un-inert effect has to be flushed BEFORE
 *    the effect that moves focus in — which depends only on hook declaration order.
 */

function mockViewport(initial: boolean) {
  const listeners = new Set<() => void>();
  const state = { matches: initial };
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return state.matches;
      },
      media: query,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
      dispatchEvent: () => false,
      onchange: null
    }))
  );
  return {
    /** Cross the breakpoint the way a rotation or window resize would. */
    setMatches(next: boolean) {
      state.matches = next;
      act(() => {
        for (const cb of [...listeners]) cb();
      });
    }
  };
}

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin"
}));

const sidebar = () => document.getElementById("app-sidebar");
const shell = () => document.querySelector(".app-shell");

describe("AppShell 모바일 드로어 (#515)", () => {
  let viewport: ReturnType<typeof mockViewport>;

  beforeEach(() => {
    window.localStorage.clear();
    viewport = mockViewport(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.body.style.overflow = "";
  });

  it("좁은 화면에서 닫힌 드로어는 inert라 탭 순서에서 빠진다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    expect(sidebar()).not.toBeNull();
    // React must actually emit the attribute — a dropped attribute would silently reinstate
    // the bug while every other assertion still passed.
    expect(sidebar()?.hasAttribute("inert"), "닫힌 드로어에 inert 속성이 있어야 한다").toBe(true);
  });

  it("제품명을 모바일 상단과 사이드바 홈에 표시한다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );

    expect(screen.getByRole("link", { name: "Geocoder Admin UI" })).toHaveAttribute(
      "href",
      "/admin"
    );
    expect(screen.getByText("Geocoder Admin UI", { selector: "strong" })).toBeInTheDocument();
  });

  it("드로어를 열면 inert가 해제된다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    expect(sidebar()?.hasAttribute("inert")).toBe(false);
  });

  it("드로어가 열릴 때 focus()가 불리는 시점에는 이미 inert가 풀려 있다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    const aside = sidebar();
    expect(aside).not.toBeNull();

    // jsdom does not implement `inert`, so it cannot observe "focus went nowhere". Observe the
    // cause instead: whether the attribute is still on the element at the instant focus() runs.
    const inertAtFocus: boolean[] = [];
    const original = HTMLElement.prototype.focus;
    vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(function (
      this: HTMLElement,
      ...args
    ) {
      if (aside?.contains(this)) inertAtFocus.push(aside.hasAttribute("inert"));
      return original.apply(this, args);
    });

    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));

    expect(inertAtFocus.length, "드로어 내부로 focus()가 호출돼야 한다").toBeGreaterThan(0);
    expect(
      inertAtFocus.some(Boolean),
      "inert가 남아 있는 동안 focus()가 불리면 포커스는 조용히 버려진다"
    ).toBe(false);
  });

  it("데스크톱 사이드바는 절대 inert가 아니다", () => {
    viewport.setMatches(false);
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    // Same element, same menuOpen === false — inerting here would kill the desktop nav.
    expect(sidebar()?.hasAttribute("inert")).toBe(false);
  });

  it("데스크톱 레일을 접으면 아이콘 전용 레일과 툴팁 라벨을 사용한다", () => {
    viewport.setMatches(false);
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );

    fireEvent.click(screen.getByRole("button", { name: "좌측 메뉴 접기" }));

    expect(shell()?.getAttribute("data-sidebar-collapsed")).toBe("true");
    expect(screen.getByRole("button", { name: "좌측 메뉴 펼치기" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "관리 홈" })).toHaveAttribute("title", "관리 홈");
  });

  it("드로어를 연 채 데스크톱 폭으로 넓히면 메뉴가 닫힌다", () => {
    render(
      <AppShell>
        <div>본문</div>
      </AppShell>
    );
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    expect(shell()?.getAttribute("data-menu-open")).toBe("true");
    expect(document.body.style.overflow).toBe("hidden");

    viewport.setMatches(false);

    // Otherwise the desktop layout is stranded: scroll stays locked and <main> stays
    // aria-hidden, with the top bar / close button / backdrop all display:none.
    expect(shell()?.getAttribute("data-menu-open")).toBe("false");
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(sidebar()?.hasAttribute("inert")).toBe(false);
  });

  it("JS 브레이크포인트와 CSS 드로어 브레이크포인트가 같은 값이다", () => {
    // Compare against the constant itself — asserting a hardcoded "980px" literal stayed green
    // when the TSX moved to another breakpoint, which is precisely the drift being guarded.
    // Drift in the CSS-smaller direction is the dangerous one: `inert` on a *visible* desktop
    // rail makes the nav unfocusable and unclickable while looking completely normal.
    const css = readFileSync(join(process.cwd(), "app/globals.css"), "utf8");
    expect(css).toContain(`@media ${DRAWER_MEDIA_QUERY}`);
  });
});
