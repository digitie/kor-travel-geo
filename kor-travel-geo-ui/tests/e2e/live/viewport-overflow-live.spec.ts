import { expect, test } from "@playwright/test";
import { loginLiveAdminPage } from "./_live";

// Layer 2 — issue #514 regression: nothing may be clipped out of reach at narrow viewports.
//
// WHY `documentElement.scrollWidth` IS NOT USED
// --------------------------------------------
// `html, body { overflow-x: clip }` (app/globals.css) makes `documentElement.scrollWidth`
// report the viewport width even while content is cut off — which is exactly why the #510
// responsive check passed while #514 was live. So this measures <main>'s scroll width and, for
// every element that sticks out past the viewport, whether some ancestor can actually scroll
// to it.
//
// It also guards the regression an earlier attempt at this fix introduced: `display: block` on
// the <table> made every table shrink-wrap to max-content instead of filling its container.

const ROUTES = [
  "/admin/source-files",
  "/admin/files",
  "/admin/ops",
  "/admin/backups",
  "/admin/consistency"
];

type Measurement = {
  mainScrollWidth: number;
  clipped: { tag: string; cls: string; right: number }[];
  shrunkTables: number;
};

test.describe("LIVE 좁은 뷰포트 오버플로 (#514)", () => {
  for (const width of [320, 375]) {
    test(`${width}px에서 잘려서 접근 불가한 콘텐츠가 없다`, async ({ page }) => {
      test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
      await loginLiveAdminPage(page, "/admin");
      await page.setViewportSize({ width, height: 800 });

      for (const route of ROUTES) {
        await page.goto(route, { waitUntil: "networkidle" });
        const measured: Measurement = await page.evaluate((vw) => {
          const main = document.querySelector("main") ?? document.body;
          const clipped: { tag: string; cls: string; right: number }[] = [];
          for (const el of Array.from(document.querySelectorAll("main *"))) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;
            if (rect.right <= vw + 1) continue;
            let scrollable = false;
            for (let p = el.parentElement; p; p = p.parentElement) {
              const overflowX = getComputedStyle(p).overflowX;
              if (overflowX === "auto" || overflowX === "scroll") {
                scrollable = true;
                break;
              }
              if (p.tagName === "MAIN") break;
            }
            if (!scrollable) {
              clipped.push({
                tag: el.tagName.toLowerCase(),
                cls: String(el.className).slice(0, 40),
                right: Math.round(rect.right)
              });
            }
          }
          // A table inside its scroller must still fill it (no max-content shrink-wrap).
          const shrunkTables = Array.from(document.querySelectorAll(".vtable-scroll")).filter(
            (scroller) => {
              const row = scroller.querySelector("tbody tr");
              if (!row) return false;
              return (
                row.getBoundingClientRect().width <
                scroller.getBoundingClientRect().width - 2
              );
            }
          ).length;
          return { mainScrollWidth: Math.round(main.scrollWidth), clipped, shrunkTables };
        }, width);

        expect(measured.clipped, `${route} @${width}px: 스크롤로 닿을 수 없는 요소`).toEqual([]);
        expect(measured.mainScrollWidth, `${route} @${width}px: main이 뷰포트를 넘음`).toBeLessThanOrEqual(width + 1);
        expect(measured.shrunkTables, `${route} @${width}px: 표가 컨테이너보다 좁게 렌더됨`).toBe(0);
      }
    });
  }
});
