import { expect, test } from "@playwright/test";

import { ADMIN_NAV_GROUPS, ADMIN_PAGES, DEBUG_PAGES, adminPageHeading } from "../../lib/admin-pages";

// 사이드바 라벨과 상단 바 h1("지오 - 페이지")은 lib/admin-pages.ts를 단일 소스로 공유한다.
const navLinks = [
  ...Object.values(DEBUG_PAGES).map((page) => ({ label: page.title, heading: adminPageHeading(page.title) })),
  { label: ADMIN_PAGES.home.title, heading: adminPageHeading(ADMIN_PAGES.home.title) },
  ...ADMIN_NAV_GROUPS.flatMap((group) =>
    group.keys.map((key) => ({
      label: ADMIN_PAGES[key].title,
      heading: adminPageHeading(ADMIN_PAGES[key].title)
    }))
  )
];
const homeHeading = adminPageHeading(ADMIN_PAGES.home.title);

test.describe("좌측 메뉴 이동", () => {
  test("메뉴를 반복 클릭해도 Next.js 로드 실패 화면으로 떨어지지 않는다", async ({ page }) => {
    test.setTimeout(90_000);

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

test.describe("최신 map Workbench 시각 계약", () => {
  test("메인 콘텐츠와 공용 컨트롤이 같은 밀도·포커스 레시피를 쓴다", async ({ page }) => {
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { exact: true, name: homeHeading })).toBeVisible();

    const contentMetrics = await page.evaluate(() => {
      const firstPanel = document.querySelector<HTMLElement>(".panel");
      const panelHeader = firstPanel?.querySelector<HTMLElement>(".panel-header");
      const panelTitle = panelHeader?.querySelector<HTMLElement>("h2");
      const body = document.body;
      const heading = document.querySelector<HTMLElement>('[data-slot="admin-shell-header"] h1');
      const description = document.querySelector<HTMLElement>('[data-slot="admin-shell-description"]');
      const panelStyle = firstPanel ? getComputedStyle(firstPanel) : null;
      const headerStyle = panelHeader ? getComputedStyle(panelHeader) : null;
      const titleStyle = panelTitle ? getComputedStyle(panelTitle) : null;
      return {
        rootFontSize: getComputedStyle(document.documentElement).fontSize,
        bodyFontSize: getComputedStyle(body).fontSize,
        bodyLineHeight: getComputedStyle(body).lineHeight,
        headingFontSize: heading ? getComputedStyle(heading).fontSize : null,
        descriptionFontSize: description ? getComputedStyle(description).fontSize : null,
        panelPadding: panelStyle?.padding,
        panelRadius: panelStyle?.borderRadius,
        panelGap: panelStyle?.gap,
        headerGap: headerStyle?.gap,
        titleFontSize: titleStyle?.fontSize,
      };
    });

    expect(contentMetrics).toMatchObject({
      rootFontSize: "16px",
      bodyFontSize: "15px",
      bodyLineHeight: "22.5px",
      headingFontSize: "17px",
      descriptionFontSize: "12px",
      panelPadding: "16px",
      panelRadius: "8px",
      panelGap: "12px",
      headerGap: "4px",
      titleFontSize: "15px",
    });

    await page.goto("/debug/geocode", { waitUntil: "domcontentloaded" });
    const controlMetrics = await page.evaluate(() => {
      const input = document.querySelector<HTMLElement>("#address");
      const button = document.querySelector<HTMLElement>('form button[type="submit"][data-slot="button"]');
      const inputStyle = input ? getComputedStyle(input) : null;
      const buttonStyle = button ? getComputedStyle(button) : null;
      return {
        inputHeight: input?.getBoundingClientRect().height,
        inputRadius: inputStyle?.borderRadius,
        buttonHeight: button?.getBoundingClientRect().height,
        buttonRadius: buttonStyle?.borderRadius,
      };
    });

    expect(controlMetrics).toEqual({
      inputHeight: 36,
      inputRadius: "6px",
      buttonHeight: 36,
      buttonRadius: "8px",
    });

    const address = page.locator("#address");
    await address.focus();
    await expect
      .poll(() =>
        address.evaluate((element) => {
          const style = getComputedStyle(element);
          return [style.outlineStyle, style.outlineWidth, style.outlineOffset, style.boxShadow];
        })
      )
      .toEqual(["solid", "2px", "2px", "none"]);
  });

  test("메인 콘텐츠가 좁은 화면에서도 가로로 잘리지 않는다", async ({ page }) => {
    for (const width of [320, 375, 414, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/admin", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { exact: true, name: homeHeading })).toBeVisible();
      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(documentWidth, `viewport ${width}px`).toBeLessThanOrEqual(width);
    }
  });

  // AdminShell: 데스크톱은 세로 rail + 접기 버튼, 태블릿·모바일은 상단 바 메뉴 버튼 → 좌측 drawer.
  for (const viewport of [
    { name: "desktop", width: 1280, height: 800, rail: true },
    { name: "tablet", width: 768, height: 1024, rail: false },
    { name: "mobile", width: 390, height: 844, rail: false }
  ] as const) {
    test(`${viewport.name}: AdminShell 메뉴 배치를 따른다`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/admin", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { level: 1, name: homeHeading })).toBeVisible();

      const rail = page.locator('[data-slot="admin-shell-rail"]');
      const menuButton = page.locator('[data-slot="admin-shell-menu-button"]');
      const toggle = page.getByRole("button", { name: "좌측 메뉴 접기" });
      if (viewport.rail) {
        await expect(rail).toBeVisible();
        await expect(rail.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link")).toHaveCount(navLinks.length);
        await expect(toggle).toBeVisible();
        await expect(menuButton).toBeHidden();
      } else {
        await expect(rail).toBeHidden();
        await expect(toggle).toBeHidden();
        await expect(menuButton).toBeVisible();
        await menuButton.click();
        const drawer = page.getByRole("dialog");
        await expect(drawer.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link")).toHaveCount(navLinks.length);
      }

      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(documentWidth).toBeLessThanOrEqual(viewport.width);
    });
  }

  test("좌측 메뉴 접기 상태가 새로고침 뒤에도 유지된다", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "좌측 메뉴 접기" }).click();
    await expect(page.getByRole("button", { name: "좌측 메뉴 펼치기" })).toBeVisible();
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByRole("button", { name: "좌측 메뉴 펼치기" })).toBeVisible();
    const railWidth = await page.locator('[data-slot="admin-shell-rail"]').evaluate((el) => el.getBoundingClientRect().width);
    expect(railWidth).toBeLessThanOrEqual(64);
  });
});
