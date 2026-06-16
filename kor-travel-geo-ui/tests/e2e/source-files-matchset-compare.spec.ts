import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeMatchSets } from "./fixtures/source-files";

// T-226 e2e: 매칭 세트 비교(구성 diff). MatchSetsTab의 비교 패널이 두 세트의 카테고리별
// 추가/제거/변경/동일과 set-level delta를 client-side로 보여 주는지 고정한다. 두 세트의 상세는
// 하네스 onRoute knob으로 id별 다르게 주입한다. (의존: T-225)

const ACTIVE = { ...makeMatchSets()[0], source_match_set_id: "ms_active", name: "활성 세트", state: "active" };
const PREV = {
  ...makeMatchSets()[0],
  source_match_set_id: "ms_prev",
  name: "이전 세트",
  state: "retired",
  integrity_alert: false,
  source_set_hash: "prevhash00000000"
};

function mkItem(category: string, over: Record<string, unknown> = {}) {
  return {
    source_match_set_item_id: `it-${category}`,
    source_match_set_id: "ms",
    category,
    role: "build_required",
    omitted: false,
    required: true,
    validation_enabled: true,
    effective_yyyymm: "202603",
    source_file_group_id: "grp_a",
    ...over
  };
}

// A(활성) vs B(이전): roadname 동일, locsum 변경(기준월), navi 제거(A만), epost 추가(B만).
const ACTIVE_DETAIL = {
  match_set: ACTIVE,
  items: [mkItem("roadname_hangul_full"), mkItem("locsum_full", { effective_yyyymm: "202604" }), mkItem("navi_full")]
};
const PREV_DETAIL = {
  match_set: PREV,
  items: [
    mkItem("roadname_hangul_full"),
    mkItem("locsum_full", { effective_yyyymm: "202603" }),
    mkItem("epost_pobox_full")
  ]
};

test.describe("매칭 세트 비교 /admin/source-files (T-226)", () => {
  test("두 세트의 카테고리 추가/제거/변경과 set-level delta를 보여 준다", async ({ page }) => {
    await installSourceFilesMock(page, {
      matchSets: [ACTIVE, PREV],
      onRoute: async ({ pathname, method, route }) => {
        const m = pathname.match(/\/source-match-sets\/([^/]+)$/);
        if (m && method === "GET") {
          const detail = m[1] === "ms_prev" ? PREV_DETAIL : ACTIVE_DETAIL;
          await route.fulfill({ contentType: "application/json", body: JSON.stringify(detail) });
          return true;
        }
        return false;
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const panel = page.locator(".panel", { hasText: "매칭 세트 비교" });
    await expect(panel).toBeVisible();

    // count 배지(추가 1 / 제거 1 / 변경 1).
    await expect(panel.getByText("추가 1")).toBeVisible();
    await expect(panel.getByText("제거 1")).toBeVisible();
    await expect(panel.getByText("변경 1")).toBeVisible();

    // 카테고리별 상태 행.
    const epostRow = panel.locator("tr", { hasText: "epost_pobox_full" });
    await expect(epostRow.getByText("추가", { exact: true })).toBeVisible();
    const naviRow = panel.locator("tr", { hasText: "navi_full" });
    await expect(naviRow.getByText("제거", { exact: true })).toBeVisible();
    const locsumRow = panel.locator("tr", { hasText: "locsum_full" });
    await expect(locsumRow.getByText("변경", { exact: true })).toBeVisible();

    // set-level hash delta (changed row 강조).
    await expect(panel.getByText("source_set_hash")).toBeVisible();
  });

  test("같은 세트를 고르면 비교 대신 안내를 보여 준다", async ({ page }) => {
    await installSourceFilesMock(page, {
      matchSets: [ACTIVE], // 세트 1개 → 비교 불가
      matchSetDetail: ACTIVE_DETAIL
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const panel = page.locator(".panel", { hasText: "매칭 세트 비교" });
    await expect(panel.getByText("비교하려면 매칭 세트가 2개 이상 필요합니다.")).toBeVisible();
  });
});
