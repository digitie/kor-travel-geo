import { expect, test } from "@playwright/test";

test.describe("VWorld 지도", () => {
  test("Python API .env의 VWorld 키로 reverse 지도 canvas와 WMTS 타일을 로드한다", async ({
    page
  }) => {
    const runtimeConfig = page.waitForResponse("**/api/runtime-config");
    const wmtsTile = page.waitForResponse(
      (response) =>
        response.url().includes("api.vworld.kr/req/wmts/1.0.0/") &&
        response.status() >= 200 &&
        response.status() < 400,
      { timeout: 30_000 }
    );

    await page.goto("/debug/reverse");

    const runtimePayload = (await (await runtimeConfig).json()) as {
      vworldApiKey?: unknown;
    };
    expect(typeof runtimePayload.vworldApiKey).toBe("string");
    expect((runtimePayload.vworldApiKey as string).trim().length).toBeGreaterThan(0);

    await expect(page.getByTestId("vworld-map-container")).toBeVisible({
      timeout: 15_000
    });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible({
      timeout: 15_000
    });
    await wmtsTile;
  });
});
