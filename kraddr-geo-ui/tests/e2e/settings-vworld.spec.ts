import { expect, test } from "@playwright/test";

test.describe("VWorld 설정 UI", () => {
  test("runtime config의 .env 키를 기본값으로 표시하고 브라우저 저장값으로 수정한다", async ({
    page
  }) => {
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ vworldApiKey: "env-key" })
      });
    });

    await page.goto("/admin/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByLabel("NEXT_PUBLIC_VWORLD_API_KEY")).toHaveValue("env-key");
    await expect(page.getByText(".env 기본값").first()).toBeVisible();

    await page.getByLabel("NEXT_PUBLIC_VWORLD_API_KEY").fill("browser-key");
    await page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "VWorld 인증키" }) })
      .getByRole("button", { name: "저장" })
      .click();

    await expect(page.getByText("지도 설정을 저장했습니다.")).toBeVisible();
    await expect(page.getByText("브라우저 저장값")).toBeVisible();
    await expect(page.getByLabel("NEXT_PUBLIC_VWORLD_API_KEY")).toHaveValue("browser-key");
    expect(await page.evaluate(() => window.localStorage.getItem("kraddr.geo.vworldApiKey"))).toBe(
      "browser-key"
    );
  });

  test("기본값 버튼은 브라우저 저장값을 지우고 .env 키로 되돌린다", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("kraddr.geo.vworldApiKey", "browser-key");
    });
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ vworldApiKey: "env-key" })
      });
    });

    await page.goto("/admin/settings");
    await expect(page.getByLabel("NEXT_PUBLIC_VWORLD_API_KEY")).toHaveValue("browser-key");
    await page.getByRole("button", { name: "기본값" }).click();

    await expect(page.getByLabel("NEXT_PUBLIC_VWORLD_API_KEY")).toHaveValue("env-key");
    expect(
      await page.evaluate(() => window.localStorage.getItem("kraddr.geo.vworldApiKey"))
    ).toBeNull();
  });
});
