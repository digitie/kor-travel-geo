import { expect, test } from "@playwright/test";

import { ADMIN_NAV_GROUPS, ADMIN_PAGES } from "../../lib/admin-pages";

// 사이드바 라벨과 페이지 h1은 lib/admin-pages.ts를 단일 소스로 공유한다.
const navLinks = [
  { label: "Geocode", heading: "Geocode" },
  { label: "Reverse", heading: "Reverse" },
  { label: "Normalize", heading: "Normalize" },
  { label: "Explain", heading: "Explain" },
  { label: ADMIN_PAGES.home.title, heading: ADMIN_PAGES.home.title },
  ...ADMIN_NAV_GROUPS.flatMap((group) =>
    group.keys.map((key) => ({
      label: ADMIN_PAGES[key].title,
      heading: ADMIN_PAGES[key].title
    }))
  )
];

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
    await expect(page.getByRole("heading", { exact: true, name: "관리 홈" })).toBeVisible();

    const contentMetrics = await page.evaluate(() => {
      const firstPanel = document.querySelector<HTMLElement>(".panel");
      const panelHeader = firstPanel?.querySelector<HTMLElement>(".panel-header");
      const panelTitle = panelHeader?.querySelector<HTMLElement>("h2");
      const body = document.body;
      const heading = document.querySelector<HTMLElement>(".page-title h1");
      const description = document.querySelector<HTMLElement>(".page-description");
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
      headingFontSize: "24px",
      descriptionFontSize: "13.5px",
      panelPadding: "16px",
      panelRadius: "8px",
      panelGap: "12px",
      headerGap: "4px",
      titleFontSize: "15px",
    });

    await page.goto("/debug/geocode", { waitUntil: "domcontentloaded" });
    const controlMetrics = await page.evaluate(() => {
      const input = document.querySelector<HTMLElement>("#address");
      const button = document.querySelector<HTMLElement>("button.button");
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
      buttonRadius: "6px",
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
      await expect(page.getByRole("heading", { exact: true, name: "관리 홈" })).toBeVisible();
      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(documentWidth, `viewport ${width}px`).toBeLessThanOrEqual(width);
    }
  });

  test("모바일 메뉴가 실제 overlay와 focus 복귀를 유지한다", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("/admin", { waitUntil: "domcontentloaded" });

    const menuToggle = page.getByRole("button", { name: "메뉴 열기" });
    await menuToggle.click();
    await expect(page.getByRole("dialog", { name: "내비게이션 메뉴" })).toBeVisible();

    const drawerMetrics = await page.evaluate(() => {
      const backdrop = document.querySelector<HTMLElement>(".sidebar-backdrop");
      const main = document.querySelector("main");
      if (!backdrop) throw new Error("sidebar backdrop is missing");
      const style = getComputedStyle(backdrop);
      return {
        background: style.backgroundColor,
        display: style.display,
        zIndex: style.zIndex,
        mainAriaHidden: main?.getAttribute("aria-hidden")
      };
    });

    expect(drawerMetrics).toMatchObject({
      display: "block",
      zIndex: "399",
      mainAriaHidden: "true"
    });
    expect(drawerMetrics.background).not.toBe("rgba(0, 0, 0, 0)");

    await page.keyboard.press("Escape");
    await expect(menuToggle).toBeFocused();
  });
});
