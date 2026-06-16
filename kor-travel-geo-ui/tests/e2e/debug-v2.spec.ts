import { expect, test, type Page } from "@playwright/test";

type JsonRecord = Record<string, unknown>;

async function captureJsonPost(
  page: Page,
  path:
    | "/api/proxy/v2/geocode"
    | "/api/proxy/v2/reverse"
    | "/api/proxy/v2/regions/within-radius",
  response: JsonRecord
) {
  const requests: JsonRecord[] = [];
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ vworldApiKey: "" })
    });
  });
  await page.route(`**${path}`, async (route) => {
    const request = route.request();
    expect(request.method()).toBe("POST");
    requests.push(request.postDataJSON() as JsonRecord);
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(response)
    });
  });
  await page.route("**/api/proxy/v1/**", async (route) => {
    throw new Error(`debug UI must not call v1 endpoint: ${route.request().url()}`);
  });
  return requests;
}

test.describe("디버그 UI v2 REST 연동", () => {
  test("도로명 지오코딩은 기본값으로 v2 geocode에 road_address와 fallback none을 보낸다", async ({
    page
  }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/geocode", {
      status: "OK",
      input: { road_address: "서울특별시 강남구 테헤란로 152", fallback: "none" },
      candidates: [{ source: "local", point: { x: 127.028601, y: 37.500344 } }]
    });

    await page.goto("/debug/geocode");
    await expect(page.getByRole("heading", { name: "Geocode" })).toBeVisible();
    await expect(page.locator("#fallback")).toHaveValue("none");
    await page.getByRole("button", { name: "실행" }).click();

    await expect(page.getByText('"candidates"')).toBeVisible();
    await expect(page.getByText('"road_address"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({
      road_address: "서울특별시 강남구 테헤란로 152",
      fallback: "none",
      include_geometry: true,
      limit: 10
    });
    expect(requests[0]).not.toHaveProperty("jibun_address");
  });

  test("지번 지오코딩은 v2 geocode에 jibun_address와 fallback api를 보낸다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/geocode", {
      status: "OK",
      input: { jibun_address: "서울특별시 강남구 역삼동 737", fallback: "api" },
      candidates: [{ source: "external", point: { x: 127.027, y: 37.499 } }]
    });

    await page.goto("/debug/geocode");
    await page.locator("#type").selectOption("parcel");
    await page.locator("#fallback").selectOption("api");
    await page.locator("#address").fill("서울특별시 강남구 역삼동 737");
    await page.getByRole("button", { name: "실행" }).click();

    await expect(page.getByText('"jibun_address"')).toBeVisible();
    await expect(page.getByText('"external"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({
      jibun_address: "서울특별시 강남구 역삼동 737",
      fallback: "api",
      include_geometry: true,
      limit: 10
    });
    expect(requests[0]).not.toHaveProperty("road_address");
  });

  test("주소가 비어 있으면 geocode 요청을 보내지 않고 검증 오류를 표시한다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/geocode", {
      status: "SHOULD_NOT_BE_USED"
    });

    await page.goto("/debug/geocode");
    await page.locator("#address").fill("");
    await page.getByRole("button", { name: "실행" }).click();

    await expect(page.getByText('"error"')).toBeVisible();
    expect(requests).toHaveLength(0);
  });

  test("지오코딩 도형 옵션을 끄면 v2 geocode에 include_geometry false를 보낸다", async ({
    page
  }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/geocode", {
      status: "OK",
      input: { road_address: "성복1로", include_geometry: false },
      candidates: [{ source: "local", point: { x: 127.0743, y: 37.3134 } }]
    });

    await page.goto("/debug/geocode");
    await page.locator("#address").fill("성복1로");
    await page.locator("#include-geometry").uncheck();
    await page.getByRole("button", { name: "실행" }).click();

    await expect(page.getByText('"include_geometry"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      road_address: "성복1로",
      include_geometry: false
    });
  });

  test("반경 행정구역은 v2 regions within-radius에 좌표와 레벨을 보낸다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/regions/within-radius", {
      center: { lon: 126.978, lat: 37.5665 },
      radius_km: 3,
      sigungu: [{ code: "11110", name: "종로구", relation: "contains" }],
      emd: [{ code: "11110119", name: "세종로", relation: "contains" }]
    });

    await page.goto("/debug/geocode");
    await page.getByRole("button", { name: "반경 조회" }).click();

    await expect(page.getByText('"sigungu"')).toBeVisible();
    await expect(page.getByText('"11110"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({
      lon: 126.978,
      lat: 37.5665,
      radius_km: 3,
      levels: ["sigungu", "emd"]
    });
  });

  test("역지오코딩은 v2 reverse에 lon/lat와 확장 옵션을 보낸다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/reverse", {
      status: "OK",
      input: { lon: 127.028601, lat: 37.500344 },
      candidates: [{ source: "local", point: { x: 127.028601, y: 37.500344 } }]
    });

    await page.goto("/debug/reverse");
    await expect(page.getByRole("heading", { name: "Reverse" })).toBeVisible();
    await page.getByRole("button", { name: "조회" }).click();

    await expect(page.getByText('"candidates"')).toBeVisible();
    await expect(page.getByText('"lon"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toEqual({
      lon: 127.028601,
      lat: 37.500344,
      crs: "EPSG:4326",
      include_region: true,
      include_zipcode: true,
      radius_m: 200,
      include_geometry: false
    });
  });

  test("역지오코딩 반경과 좌표 입력 변경값을 v2 reverse body에 반영한다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/reverse", {
      status: "OK",
      input: { lon: 129.075642, lat: 35.179554 },
      candidates: [{ source: "local", point: { x: 129.075642, y: 35.179554 } }]
    });

    await page.goto("/debug/reverse");
    await page.locator("#x").fill("129.075642");
    await page.locator("#y").fill("35.179554");
    await page.locator("#radius").fill("1500");
    await page.getByRole("button", { name: "조회" }).click();

    await expect(page.getByText('"candidates"')).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      lon: 129.075642,
      lat: 35.179554,
      radius_m: 1500
    });
  });

  test("범위를 벗어난 좌표는 reverse 요청을 보내지 않고 검증 오류를 표시한다", async ({ page }) => {
    const requests = await captureJsonPost(page, "/api/proxy/v2/reverse", {
      status: "SHOULD_NOT_BE_USED"
    });

    await page.goto("/debug/reverse");
    await page.locator("#x").fill("140");
    await page.getByRole("button", { name: "조회" }).click();

    await expect(page.getByText('"error"')).toBeVisible();
    expect(requests).toHaveLength(0);
  });
});
