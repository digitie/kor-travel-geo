import { expect, test } from "@playwright/test";

const navLinks = [
  { label: "Geocode", heading: "Geocode" },
  { label: "Reverse", heading: "Reverse" },
  { label: "Normalize", heading: "Normalize" },
  { label: "Explain", heading: "Explain" },
  { label: "Load", heading: "Load" },
  { label: "Backups", heading: "DB Backups" },
  { label: "Tables", heading: "Tables" },
  { label: "Cache", heading: "Cache" },
  { label: "Logs", heading: "Logs" },
  { label: "Consistency", heading: "Consistency" },
  { label: "Ops", heading: "Ops" },
  { label: "Settings", heading: "Settings" },
  { label: "Metrics", heading: "Cache" },
  { label: "MV refresh", heading: "Load" },
  { label: "PostGIS", heading: "Tables" }
];

test.describe("좌측 메뉴 이동", () => {
  test("메뉴를 반복 클릭해도 Next.js 로드 실패 화면으로 떨어지지 않는다", async ({ page }) => {
    const pageErrors: string[] = [];
    const failedRequests: string[] = [];
    const rscRequests: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("_rsc=")) {
        rscRequests.push(request.url());
      }
    });
    page.on("requestfailed", (request) => {
      const failureText = request.failure()?.errorText ?? "";
      if (failureText.includes("ERR_ABORTED") || failureText.includes("NS_BINDING_ABORTED")) {
        return;
      }
      failedRequests.push(`${request.url()} ${failureText}`);
    });

    await page.goto("/debug/geocode", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Geocode" })).toBeVisible();

    for (let cycle = 0; cycle < 4; cycle += 1) {
      for (const link of navLinks) {
        await page.getByRole("link", { exact: true, name: link.label }).click();
        await page.waitForLoadState("domcontentloaded").catch(() => {});
        await expect(page.getByRole("heading", { exact: true, name: link.heading })).toBeVisible();
        await expect(page.locator("main")).toBeVisible();
        await expect(page.locator("body")).not.toContainText("This page couldn");
        await expect(page.locator("body")).not.toContainText("Reload to try again");
        await expect(page.locator("body")).not.toContainText("go back.");
      }
    }

    expect(pageErrors).toEqual([]);
    expect(failedRequests).toEqual([]);
    expect(rscRequests).toEqual([]);
  });
});
