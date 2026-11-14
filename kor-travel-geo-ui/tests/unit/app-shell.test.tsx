import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";
import { ADMIN_NAV_GROUPS, ADMIN_PAGES } from "@/lib/admin-pages";

const pathname = { current: "/admin" };
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current
}));

const SIDEBAR_COLLAPSED_KEY = "kor-travel-geo:sidebar-collapsed";

function renderShell(path = "/admin") {
  pathname.current = path;
  return render(
    <AppShell>
      <p>본문</p>
    </AppShell>
  );
}

describe("AppShell — map admin-shell 구조", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
        onchange: null
      }))
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("단일 주요 메뉴에 map과 같은 순서로 그룹을 렌더한다(개요 → 조회·진단 → 기능 그룹)", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" });
    const links = within(nav).getAllByRole("link").map((link) => link.getAttribute("aria-label"));
    expect(links[0]).toBe(ADMIN_PAGES.home.title);
    expect(links.slice(1, 5)).toEqual(["Geocode", "Reverse", "Normalize", "Explain"]);
    expect(links.slice(5)).toEqual(
      ADMIN_NAV_GROUPS.flatMap((group) => group.keys.map((key) => ADMIN_PAGES[key].title))
    );
    for (const title of ["조회·진단", ...ADMIN_NAV_GROUPS.map((group) => group.title)]) {
      expect(within(nav).getByText(title)).toBeInTheDocument();
    }
  });

  it("가장 긴 경로 일치 항목만 현재 페이지로 표시한다", () => {
    renderShell(`${ADMIN_PAGES.consistency.path}/report-1`);
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" });
    const current = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page")
      .map((link) => link.getAttribute("aria-label"));
    expect(current).toEqual([ADMIN_PAGES.consistency.title]);
  });

  it("rail 접기 상태를 localStorage에 저장하고 다시 읽는다", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "좌측 메뉴 접기" }));
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe("1");
    expect(screen.getByRole("button", { name: "좌측 메뉴 펼치기" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "좌측 메뉴 펼치기" }));
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY)).toBe("0");
  });

  it("로그인 화면은 shell 없이 children만 렌더한다", () => {
    renderShell("/login");
    expect(screen.getByText("본문")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "주요 메뉴" })).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="admin-shell-rail"]')).toBeNull();
  });

  it("로그아웃 실패를 알리고 화면에 머문다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
    renderShell();
    const [logout] = screen.getAllByRole("button", { name: "로그아웃" });
    await act(async () => {
      fireEvent.click(logout);
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("로그아웃하지 못했습니다");
  });
});
