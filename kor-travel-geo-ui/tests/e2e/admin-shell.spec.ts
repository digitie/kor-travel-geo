import { buttonVariants } from "@kor-travel/ui/button-variants";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { twMerge } from "tailwind-merge";

import { ADMIN_PAGES, DEBUG_PAGES, adminPageHeading } from "../../lib/admin-pages";

// @kor-travel/ui 0.2.3 AdminShell 위의 Geo 계약(소유자 요구 2026-11-19). 셸·drawer 자체는 #645와
// navigation.spec이 다룬다. 여기서는 (1) 모든 페이지 맨 위 한 줄에 "지오 - 페이지" 제목과 작은 설명만 있고
// 앱 설명이 없는지, (2) 버튼 테두리가 상태에 따라 굵어지거나 이중이 되지 않는지(FS-7.8)를 PC·모바일에서 본다.

const VIEWPORTS = [
  { name: "pc", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 }
] as const;

const PAGES = [
  ...Object.values(ADMIN_PAGES).map((page) => ({ path: page.path, title: page.title, description: page.description })),
  {
    path: `${ADMIN_PAGES.consistency.path}/report-e2e`,
    title: ADMIN_PAGES.consistency.title,
    description: ADMIN_PAGES.consistency.description
  },
  ...Object.values(DEBUG_PAGES)
];

const BUTTON_VARIANTS = ["default", "outline", "secondary", "ghost", "destructive", "destructive-solid", "link"] as const;

async function topBarMetrics(page: Page) {
  return page.evaluate(() => {
    const header = document.querySelector<HTMLElement>('[data-slot="admin-shell-header"]');
    const heading = header?.querySelector<HTMLElement>("h1");
    const description = header?.querySelector<HTMLElement>('[data-slot="admin-shell-description"]');
    const headerBox = header?.getBoundingClientRect();
    const headingBox = heading?.getBoundingClientRect();
    const descriptionBox = description?.getBoundingClientRect();
    return {
      headerHeight: headerBox?.height ?? 0,
      headingLines: heading ? Math.round(heading.getBoundingClientRect().height / parseFloat(getComputedStyle(heading).lineHeight)) : 0,
      headingText: heading?.textContent ?? "",
      descriptionText: description?.textContent ?? "",
      descriptionFontSize: description ? parseFloat(getComputedStyle(description).fontSize) : 0,
      headingFontSize: heading ? parseFloat(getComputedStyle(heading).fontSize) : 0,
      // 제목과 설명이 같은 줄(세로 중심 차이가 한 줄 높이 미만)에 있다.
      sameLine:
        headingBox && descriptionBox
          ? Math.abs(headingBox.top + headingBox.height / 2 - (descriptionBox.top + descriptionBox.height / 2)) < headingBox.height
          : null,
      h1Count: document.querySelectorAll("h1").length,
      // html/body가 overflow-x: clip이라 documentElement.scrollWidth는 넘침을 못 본다 → 상단 바 자체를 잰다.
      headerOverflow: header ? header.scrollWidth - header.clientWidth : 0,
      title: document.title
    };
  });
}

test.describe("AdminShell — 상단 바 한 줄 제목", () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}: 모든 페이지가 "지오 - 페이지" 한 줄 제목과 작은 설명을 갖는다`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const target of PAGES) {
        await page.goto(target.path, { waitUntil: "domcontentloaded" });
        const expected = adminPageHeading(target.title);
        await expect(page.getByRole("heading", { level: 1, exact: true, name: expected })).toBeVisible();
        await expect(page).toHaveTitle(expected);
        const metrics = await topBarMetrics(page);
        expect(metrics.h1Count, target.path).toBe(1);
        expect(metrics.headingLines, target.path).toBe(1);
        expect(metrics.headerHeight, target.path).toBeLessThanOrEqual(56);
        expect(metrics.descriptionText, target.path).toBe(target.description ?? "");
        expect(metrics.descriptionFontSize, target.path).toBeLessThan(metrics.headingFontSize);
        expect(metrics.sameLine, target.path).toBe(true);
        expect(metrics.headerOverflow, `${target.path}: 상단 바가 가로로 넘치지 않는다`).toBeLessThanOrEqual(0);
        // 앱 설명 문구(옛 워드마크 "Geocoder Admin UI")는 셸 어디에도 없다.
        await expect(page.locator('[data-slot="admin-shell"]')).not.toContainText("Admin UI");
      }
    });
  }
});

type Box = { x: number; y: number; width: number; height: number };
type ControlStyle = {
  border: string[];
  outlineStyle: string;
  outlineWidth: string;
  outlineOffset: string;
  boxShadow: string;
};

async function controlStyle(locator: Locator): Promise<ControlStyle> {
  return locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      border: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth],
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      outlineOffset: style.outlineOffset,
      boxShadow: style.boxShadow
    };
  });
}

function expectSingleBorder(style: ControlStyle, rest: ControlStyle, label: string) {
  expect(style.border, `${label}: 테두리 두께가 상태에 따라 바뀌지 않는다`).toEqual(rest.border);
  expect(style.boxShadow, `${label}: 그림자 테두리가 덧대지지 않는다`).toBe("none");
}

/** 공통 buttonVariants 그대로의 버튼을 본문에 꽂아 앱 CSS가 상태를 덮어쓰지 않는지 본다. */
async function mountVariantGallery(page: Page) {
  const variants = BUTTON_VARIANTS.map((variant) => ({ variant, className: twMerge(buttonVariants({ variant })) }));
  await page.evaluate((items) => {
    const main = document.querySelector("main");
    if (!main) throw new Error("main 없음");
    const gallery = document.createElement("section");
    gallery.id = "button-variant-gallery";
    gallery.setAttribute("aria-label", "버튼 변형");
    gallery.style.cssText = "display:flex;flex-wrap:wrap;gap:12px;padding:16px;background:var(--kt-surface-card)";
    const before = document.createElement("input");
    before.id = "gallery-before";
    before.setAttribute("aria-label", "갤러리 앞 입력");
    gallery.append(before);
    for (const { variant, className } of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = className;
      button.dataset.slot = "button";
      button.dataset.variant = variant;
      button.dataset.size = "default";
      button.textContent = variant;
      gallery.append(button);
    }
    const disabled = document.createElement("button");
    disabled.type = "button";
    disabled.disabled = true;
    disabled.className = items[0].className;
    disabled.dataset.slot = "button";
    disabled.dataset.variant = "default";
    disabled.textContent = "disabled";
    gallery.append(disabled);
    main.prepend(gallery);
  }, variants);
  return page.locator("#button-variant-gallery");
}

test.describe("버튼 테두리(FS-7.8) — 변형별 상태", () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name}: hover·focus·active에서 테두리가 굵어지거나 이중이 되지 않는다`, async ({ page, browserName }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(DEBUG_PAGES.geocode.path, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { level: 1, name: adminPageHeading(DEBUG_PAGES.geocode.title) })).toBeVisible();
      const gallery = await mountVariantGallery(page);
      const shot = (state: string) =>
        gallery.screenshot({ path: test.info().outputPath(`buttons-${browserName}-${viewport.width}-${state}.png`) });
      await shot("rest");

      for (const variant of BUTTON_VARIANTS) {
        const button = gallery.locator(`button[data-variant="${variant}"]`).first();
        const rest = await controlStyle(button);
        const restBox = (await button.boundingBox()) as Box;
        expect(rest.boxShadow, `${variant}: rest`).toBe("none");
        expect(rest.border.every((width) => width === rest.border[0]), `${variant}: 네 변 같은 두께`).toBe(true);
        expect(parseFloat(rest.border[0]), `${variant}: 1px 이하`).toBeLessThanOrEqual(1);

        await button.hover();
        expectSingleBorder(await controlStyle(button), rest, `${variant} hover`);
        expect(((await button.boundingBox()) as Box).y, `${variant}: hover에서 움직이지 않는다`).toBeCloseTo(restBox.y, 1);
        if (variant === "outline") await shot("hover-outline");

        // 키보드 포커스: 앞 입력에서 Tab → focus-visible. outline 2px 하나, offset 2px.
        await page.locator("#gallery-before").focus();
        await page.keyboard.press("Tab");
        let guard = 0;
        while (!(await button.evaluate((el) => el === document.activeElement)) && guard < BUTTON_VARIANTS.length + 1) {
          await page.keyboard.press("Tab");
          guard += 1;
        }
        await expect(button).toBeFocused();
        const focused = await controlStyle(button);
        expectSingleBorder(focused, rest, `${variant} focus-visible`);
        expect([focused.outlineStyle, focused.outlineWidth, focused.outlineOffset], `${variant}: focus outline`).toEqual([
          "solid",
          "2px",
          "2px"
        ]);
        if (variant === "outline") await shot("focus-outline");

        // 누름(active): 테두리 두께 그대로, 이동은 1px 이하.
        await page.mouse.move(restBox.x + restBox.width / 2, restBox.y + restBox.height / 2);
        await page.mouse.down();
        const pressed = await controlStyle(button);
        const pressedBox = (await button.boundingBox()) as Box;
        if (variant === "outline") await shot("active-outline");
        await page.mouse.up();
        expectSingleBorder(pressed, rest, `${variant} active`);
        expect(Math.abs(pressedBox.y - restBox.y), `${variant}: 누름 이동 ≤ 1px`).toBeLessThanOrEqual(1.01);
        // 마우스 클릭으로 생긴 포커스는 focus-visible이 아니므로 outline이 남지 않는다.
        expect((await controlStyle(button)).outlineStyle, `${variant}: 클릭 뒤 outline 없음`).toBe("none");
      }
      await shot("after");
    });
  }

  test("셸 조작 요소(메뉴 링크·접기·로그아웃·메뉴 버튼)의 키보드 포커스는 outline 2px 하나다", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(ADMIN_PAGES.home.path, { waitUntil: "domcontentloaded" });
    const targets: Locator[] = [
      page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { exact: true, name: ADMIN_PAGES.settings.title }),
      page.getByRole("button", { name: "좌측 메뉴 접기" }),
      page.getByRole("button", { name: "로그아웃" })
    ];
    for (const target of targets) {
      const rest = await controlStyle(target);
      await target.focus();
      // 프로그램 focus는 focus-visible이 아닐 수 있으므로 Shift+Tab/Tab으로 키보드 modality를 만든다.
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Tab");
      await expect(target).toBeFocused();
      const focused = await controlStyle(target);
      expect(focused.border).toEqual(rest.border);
      expect(focused.boxShadow).toBe("none");
      expect([focused.outlineStyle, focused.outlineWidth, focused.outlineOffset]).toEqual(["solid", "2px", "2px"]);
    }

    // 실제 앱 버튼(조회 폼의 size="lg" 제출 버튼): 키보드 포커스·누름에서 테두리 그대로.
    await page.goto(DEBUG_PAGES.geocode.path, { waitUntil: "domcontentloaded" });
    const submit = page.locator('form button[type="submit"][data-slot="button"]').first();
    await expect(submit).toBeVisible();
    const submitRest = await controlStyle(submit);
    await submit.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    await expect(submit).toBeFocused();
    const submitFocused = await controlStyle(submit);
    expect(submitFocused.border).toEqual(submitRest.border);
    expect(submitFocused.boxShadow).toBe("none");
    expect([submitFocused.outlineStyle, submitFocused.outlineWidth, submitFocused.outlineOffset]).toEqual(["solid", "2px", "2px"]);
    await submit.hover();
    expect((await controlStyle(submit)).border).toEqual(submitRest.border);

    await page.goto(ADMIN_PAGES.home.path, { waitUntil: "domcontentloaded" });
    await page.setViewportSize({ width: 390, height: 844 });
    const menuButton = page.locator('[data-slot="admin-shell-menu-button"]');
    const rest = await controlStyle(menuButton);
    await page.locator("main").focus();
    await page.keyboard.press("Shift+Tab");
    let guard = 0;
    while (!(await menuButton.evaluate((el) => el === document.activeElement)) && guard < 5) {
      await page.keyboard.press("Shift+Tab");
      guard += 1;
    }
    await expect(menuButton).toBeFocused();
    const focused = await controlStyle(menuButton);
    expect(focused.border).toEqual(rest.border);
    expect([focused.outlineStyle, focused.outlineWidth, focused.outlineOffset]).toEqual(["solid", "2px", "2px"]);
  });
});
