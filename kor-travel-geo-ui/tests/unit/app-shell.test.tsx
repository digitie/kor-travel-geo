import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/ui/PageHeader";
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

describe("AppShell — Common AdminShell 연결", () => {
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

  it("rail 접기 상태를 기존 숫자 형식으로 저장하고 다시 읽는다", () => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "0");
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
  it("Common 상단 바 한 곳에 페이지 제목·설명·동작을 등록하고 본문 메타를 유지한다", () => {
    pathname.current = ADMIN_PAGES.ops.path;
    render(
      <AppShell>
        <PageHeader title="운영 이력" description="최근 운영 기록" actions={<button>새로 고침</button>} meta="기록 3건" />
        <p>본문</p>
      </AppShell>
    );
    const shell = document.querySelector('[data-slot="admin-shell"]');
    expect(shell).not.toBeNull();
    const main = screen.getByRole("main");
    const heading = screen.getByRole("heading", { level: 1, name: "운영 이력" });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    expect(main.contains(header)).toBe(false);
    expect(within(header!).getByText("최근 운영 기록")).toBeInTheDocument();
    expect(within(header!).getByRole("button", { name: "새로 고침" })).toBeInTheDocument();
    expect(within(main).getByText("기록 3건")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "본문으로 건너뛰기" })).toHaveAttribute("href", "#main-content");
    expect(main).toHaveAttribute("id", "main-content");
  });

  it("모바일 drawer는 같은 메뉴·로그아웃을 제공하고 Escape로 닫힌다", async () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    const drawer = await screen.findByRole("dialog", { name: "주요 메뉴" });
    const nav = within(drawer).getByRole("navigation", { name: "주요 메뉴" });
    expect(within(nav).getByRole("link", { name: ADMIN_PAGES.sourceFiles.title })).toHaveAttribute(
      "href", ADMIN_PAGES.sourceFiles.path
    );
    expect(within(drawer).getByRole("button", { name: "로그아웃" })).toBeInTheDocument();
    fireEvent.keyDown(drawer, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("경로가 바뀌면 열린 drawer를 닫고 본문으로 포커스를 옮긴다", async () => {
    const view = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    await screen.findByRole("dialog");
    pathname.current = ADMIN_PAGES.sourceFiles.path;
    view.rerender(<AppShell><p>다음 본문</p></AppShell>);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("main")).toHaveFocus());
    const current = screen.getByRole("navigation", { name: "주요 메뉴" });
    expect(within(current).getByRole("link", { name: ADMIN_PAGES.sourceFiles.title })).toHaveAttribute(
      "aria-current", "page"
    );
  });

  it("기존 저장된 접힘 값을 읽어 축약 브랜드와 접근 가능한 메뉴를 제공한다", () => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, "1");
    renderShell();
    expect(screen.getByRole("button", { name: "좌측 메뉴 펼치기" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Geocoder Admin UI" })).toHaveTextContent("GA");
    expect(screen.getByRole("link", { name: "Geocode" })).toHaveAttribute("href", "/debug/geocode");
  });

});
