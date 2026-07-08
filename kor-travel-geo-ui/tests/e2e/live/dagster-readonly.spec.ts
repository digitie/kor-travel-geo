import { expect, test } from "@playwright/test";

import { ADMIN_PAGES } from "../../../lib/admin-pages";
import {
  LIVE_TIMEOUT,
  expectNoErrorScreen,
  isLiveE2EEnabled,
  loginLiveAdminPage
} from "./_live";

// LIVE read-only coverage of the T-290 Dagster observe page (`/admin/dagster`).
//
// Drives the real UI against the real observe API (`/v1/ops/dagster/summary`) and the
// running geo Dagster webserver. Read-only: it navigates and asserts the observe panels
// render; it never enables a schedule, launches a run, or triggers a backup.
//
// This is the M2 "live UI e2e #1" gate for the observe surface (dagster-migration-plan §3).

test.describe("LIVE admin Dagster observe page", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin/dagster");
  });

  test("/admin/dagster renders the observe panels (summary, runs, code locations, Dagster UI)", async ({
    page
  }) => {
    await page.goto("/admin/dagster");
    await expect(
      page.getByRole("heading", { name: ADMIN_PAGES.dagster.title, exact: true })
    ).toBeVisible({ timeout: LIVE_TIMEOUT });
    await expectNoErrorScreen(page);

    // Core observe panels render against the live backend (they render even on a Dagster
    // outage via the 200/status=unavailable path; here the geo Dagster webserver is up).
    for (const title of ["Dagster UI", "Recent runs", "Code locations", "Schedules and sensors"]) {
      await expect(page.getByText(title, { exact: false }).first()).toBeVisible({
        timeout: LIVE_TIMEOUT
      });
    }

    // The Dagster UI panel embeds the browser-facing URL as an iframe once the observe
    // summary loads. In prod this is the router-proxied public domain; in dev it falls back
    // to the internal URL. Either way it must be an absolute http(s) URL.
    const frame = page.locator('iframe[title="Dagster UI"]');
    await expect(frame).toBeVisible({ timeout: LIVE_TIMEOUT });
    const src = await frame.getAttribute("src");
    expect(src ?? "").toMatch(/^https?:\/\//);
  });
});
