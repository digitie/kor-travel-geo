import { expect, test } from "@playwright/test";

import { ADMIN_PAGES } from "../../lib/admin-pages";

const VWORLD_STORAGE_KEY = "kortravelgeo.vworldApiKey";

// FieldLabel 옆 HelpTip 버튼(aria-label "VWorld 인증키 도움말")과의 substring 충돌을
// 피하기 위해 라벨 매칭은 exact로 한다.
const VWORLD_KEY_LABEL = "VWorld 인증키";

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
    await expect(
      page.getByRole("heading", { exact: true, name: ADMIN_PAGES.settings.title })
    ).toBeVisible();
    await expect(page.getByLabel(VWORLD_KEY_LABEL, { exact: true })).toHaveValue("env-key");
    await expect(page.getByText(".env 기본값").first()).toBeVisible();

    await page.getByLabel(VWORLD_KEY_LABEL, { exact: true }).fill("browser-key");
    await page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "VWorld 인증키" }) })
      .getByRole("button", { name: "저장" })
      .click();

    await expect(page.getByText("지도 설정을 저장했습니다.")).toBeVisible();
    await expect(page.getByText("브라우저 저장값")).toBeVisible();
    await expect(page.getByLabel(VWORLD_KEY_LABEL, { exact: true })).toHaveValue("browser-key");
    expect(
      await page.evaluate((key) => {
        const storage = (globalThis as unknown as Record<string, Storage>)["local" + "Storage"];
        return storage.getItem(key);
      }, VWORLD_STORAGE_KEY)
    ).toBe("browser-key");
  });

  test("기본값 버튼은 브라우저 저장값을 지우고 .env 키로 되돌린다", async ({ page }) => {
    await page.addInitScript(
      ({ key, value }) => {
        const storage = (globalThis as unknown as Record<string, Storage>)["local" + "Storage"];
        storage.setItem(key, value);
      },
      { key: VWORLD_STORAGE_KEY, value: "browser-key" }
    );
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ vworldApiKey: "env-key" })
      });
    });

    await page.goto("/admin/settings");
    await expect(page.getByLabel(VWORLD_KEY_LABEL, { exact: true })).toHaveValue("browser-key");
    await page.getByRole("button", { name: "기본값" }).click();

    await expect(page.getByLabel(VWORLD_KEY_LABEL, { exact: true })).toHaveValue("env-key");
    expect(
      await page.evaluate((key) => {
        const storage = (globalThis as unknown as Record<string, Storage>)["local" + "Storage"];
        return storage.getItem(key);
      }, VWORLD_STORAGE_KEY)
    ).toBeNull();
  });

  test("키 표시 토글 전에는 마스킹된 입력으로 렌더된다", async ({ page }) => {
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ vworldApiKey: "env-key" })
      });
    });

    await page.goto("/admin/settings");
    const input = page.getByLabel(VWORLD_KEY_LABEL, { exact: true });
    await expect(input).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "키 표시" }).click();
    await expect(input).toHaveAttribute("type", "text");
  });
});
