import { expect, test } from "@playwright/test";
import { loginLiveAdminPage } from "./_live";

// Layer 2 — issue #515 regression: opening the mobile drawer must move focus into it.
//
// WHY THIS CANNOT BE A UNIT TEST
// ------------------------------
// jsdom has no CSS cascade and no layout, so it cannot see the failure mode this guards. The
// same bug shipped twice through two different mechanisms, and both were invisible to the unit
// suite:
//
//  1. `inert` on the closed drawer was cleared in an effect declared AFTER the one that calls
//     focus(). Focusing into an inert subtree is a silent no-op that un-inerting does not
//     replay, so the drawer opened with focus left on the hamburger.
//  2. The `visibility: hidden` baseline (added so the closed drawer is out of the tab order
//     before hydration) hid the drawer at the instant focus() ran — but ONLY under
//     `prefers-reduced-motion`. The global reduced-motion rule forces
//     `transition-duration: 0.01ms`, and a `visibility` transition with a combined duration
//     above zero still starts, computing to its START value (hidden) at progress 0. Zero
//     duration starts no transition at all, so the value flips immediately.
//
// Both settings are exercised because (2) passes at the default motion setting.

const DRAWER_VIEWPORT = { width: 390, height: 844 };

test.describe("LIVE 모바일 드로어 포커스 (#515)", () => {
  for (const reducedMotion of ["no-preference", "reduce"] as const) {
    test(`prefers-reduced-motion: ${reducedMotion} — 드로어를 열면 포커스가 안으로 들어간다`, async ({
      page
    }) => {
      test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
      await loginLiveAdminPage(page, "/admin");
      await page.emulateMedia({ reducedMotion });
      await page.setViewportSize(DRAWER_VIEWPORT);
      await page.goto("/admin", { waitUntil: "networkidle" });

      const sidebar = page.locator("#app-sidebar");
      // Closed: out of the tab order and out of the a11y tree.
      await expect(sidebar).toHaveAttribute("inert", /.*/);

      await page.getByRole("button", { name: "메뉴 열기" }).click();

      await expect(sidebar).not.toHaveAttribute("inert", /.*/);
      const state = await page.evaluate(() => {
        const aside = document.getElementById("app-sidebar");
        const active = document.activeElement as HTMLElement | null;
        return {
          asideVisibility: aside ? getComputedStyle(aside).visibility : null,
          focusInsideDrawer: Boolean(aside && active && aside.contains(active)),
          activeLabel: active?.className || active?.tagName || null
        };
      });

      expect(state.asideVisibility, "열린 드로어는 visible이어야 한다").toBe("visible");
      expect(
        state.focusInsideDrawer,
        `포커스가 드로어 밖에 남았다 (activeElement=${state.activeLabel})`
      ).toBe(true);
    });
  }

  test("드로어를 연 채 데스크톱 폭으로 넓히면 본문이 다시 살아난다", async ({ page }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin");
    await page.setViewportSize(DRAWER_VIEWPORT);
    await page.goto("/admin", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "메뉴 열기" }).click();

    // Crossing the breakpoint with the drawer open used to leave body scroll locked and <main>
    // aria-hidden, with every control that could close it display:none.
    await page.setViewportSize({ width: 1280, height: 900 });

    await expect(page.locator(".app-shell")).toHaveAttribute("data-menu-open", "false");
    await expect(page.locator("main")).not.toHaveAttribute("aria-hidden", "true");
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
    await expect(page.locator("#app-sidebar")).not.toHaveAttribute("inert", /.*/);
  });
});
