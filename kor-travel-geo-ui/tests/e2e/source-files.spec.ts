import { expect, test, type Page } from "@playwright/test";

// /admin/source-files (T-209) e2e. 백엔드 admin API는 page.route로 목킹하므로 DB/백엔드 없이
// UI 단독으로 5개 기능 탭 + 동적 검증 케이스 탭과 핵심 상호작용을 검증한다.

const CATALOG = {
  categories: [
    {
      category: "roadname_hangul_full",
      label: "도로명주소 한글 전체분",
      role: "build_required",
      default_role: "build_required",
      group_kind: "single_file",
      optional: false,
      expected_member_kinds: ["juso"]
    },
    {
      category: "epost_pobox_full",
      label: "epost 사서함",
      role: "enrichment_candidate",
      default_role: "enrichment_candidate",
      group_kind: "single_file",
      optional: true,
      expected_member_kinds: []
    }
  ]
};

const MATCH_SETS = [
  {
    source_match_set_id: "ms_active",
    name: "활성 세트",
    profile: "serving_recommended",
    state: "active",
    integrity_alert: true,
    integrity_alert_at: "2026-06-12T00:00:00Z",
    integrity_alert_detail: { reason: "hash_mismatch" },
    mixed_yyyymm: false,
    source_set_hash: "abcdef0123456789",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-12T00:00:00Z",
    validated_at: "2026-06-02T00:00:00Z"
  }
];

const MATCH_SET_DETAIL = {
  match_set: MATCH_SETS[0],
  items: [
    {
      source_match_set_item_id: "item_1",
      source_match_set_id: "ms_active",
      category: "roadname_hangul_full",
      role: "build_required",
      omitted: false,
      required: true,
      validation_enabled: true,
      effective_yyyymm: "202603",
      source_file_group_id: "grp_1"
    }
  ]
};

const RECONCILE_RUNS = [
  {
    source_storage_reconcile_run_id: "rec_1",
    mode: "quick",
    prefix: "source/",
    state: "completed",
    scanned_objects: 100,
    scanned_db_files: 100,
    mismatch_count: 1,
    resolved_count: 0,
    rehashed_objects: 0,
    skipped_rehash_objects: 0,
    started_at: "2026-06-13T00:00:00Z"
  }
];

const RECONCILE_ITEMS = {
  items: [
    {
      source_storage_reconcile_item_id: "ri_2",
      source_storage_reconcile_run_id: "rec_1",
      issue_type: "object_missing_db",
      severity: "warning",
      state: "open",
      object_key: "source/electronic_map_full/orphan-36.zip"
    }
  ]
};

const CAPACITY = {
  total_bytes: 2048,
  total_object_count: 5,
  over_threshold: false,
  quarantined_bytes: 0,
  soft_deleted_bytes: 0,
  unregistered_bytes: 1024,
  growth_30d_bytes: 512,
  capacity_limit_bytes: null,
  retention: null,
  categories: [
    {
      category: "roadname_hangul_full",
      object_count: 5,
      total_bytes: 2048,
      quarantined_bytes: 0,
      soft_deleted_bytes: 0
    }
  ]
};

const CASE_DEFINITIONS = Array.from({ length: 17 }, (_, index) => ({
  code: `C${index + 1}`,
  name: `${index + 1}번 케이스`,
  compares: "원천 비교",
  abnormal_criteria: "임계값 초과",
  evidence: ["증거"],
  likely_causes: ["원인"],
  decision_guide: "지도 확인",
  threshold: "WARN"
}));

const CONSISTENCY_REPORTS = [
  {
    report_id: "rep_1",
    scope: "full",
    severity_max: "WARN",
    source_set: {},
    started_at: "2026-06-10T00:00:00Z",
    finished_at: "2026-06-10T00:01:00Z",
    generated_by: "cli"
  }
];

function resolveAdminBody(pathname: string): unknown {
  if (pathname.endsWith("/admin/source-file-categories")) return CATALOG;
  if (pathname.includes("/admin/source-files/upload-sessions")) return [];
  if (pathname.endsWith("/admin/source-files/capacity")) return CAPACITY;
  if (pathname.includes("/admin/source-files/reconcile/") && pathname.includes("/items"))
    return RECONCILE_ITEMS;
  if (pathname.includes("/admin/source-files/reconcile")) return RECONCILE_RUNS;
  if (/\/admin\/source-match-sets\/[^/]+$/.test(pathname)) return MATCH_SET_DETAIL;
  if (pathname.includes("/admin/source-match-sets")) return MATCH_SETS;
  if (pathname.includes("/admin/consistency/case-definitions")) return CASE_DEFINITIONS;
  if (pathname.endsWith("/admin/consistency")) return CONSISTENCY_REPORTS;
  if (pathname.includes("/admin/consistency/"))
    return { ...CONSISTENCY_REPORTS[0], cases: [] };
  if (pathname.includes("/admin/ops/releases")) return [];
  if (pathname.includes("/admin/ops/snapshots")) return [];
  return null;
}

async function mockSourceFilesApi(page: Page): Promise<void> {
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ vworldApiKey: "" }) });
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/events")) {
      // upload-session SSE: end the stream immediately so the hook closes (no reconnect).
      await route.fulfill({ contentType: "text/event-stream", body: "" });
      return;
    }
    if (pathname.endsWith("/bulk-hard-delete")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          requested_count: 1,
          hard_deleted_count: 1,
          delete_failed_count: 0,
          skipped_count: 0,
          results: [
            { object_key: "source/electronic_map_full/orphan-36.zip", outcome: "hard_deleted" }
          ],
          affected_match_set_ids: []
        })
      });
      return;
    }
    const body = resolveAdminBody(pathname);
    if (body === null) {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

test.describe("원천 파일 관리 /admin/source-files", () => {
  test("5개 기능 탭 + 검증 케이스 탭을 렌더한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");

    const tabList = page.getByRole("tablist", { name: "원천 파일 관리 탭" });
    await expect(tabList).toBeVisible();
    for (const name of ["업로드", "목록", "매칭 세트", "RustFS 정합성", "현재 구성", "검증 케이스"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
  });

  test("업로드 탭: 카테고리 카드와 epost 받기 버튼(활성)을 보여 준다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");

    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
    const epostCard = page.locator(".source-card", { hasText: "epost 사서함" });
    await expect(epostCard.getByRole("button", { name: "epost 받기" })).toBeEnabled();
  });

  test("매칭 세트 탭: 활성 세트와 무결성 경보를 표시한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    await expect(page.getByText("활성 세트")).toBeVisible();
    await expect(page.getByText(/무결성 경보/).first()).toBeVisible();
  });

  test("RustFS 정합성 탭: 실행/정리 대상/용량을 표시한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();

    await expect(page.getByText("정합성 실행 (RustFS ⟷ DB)")).toBeVisible();
    await expect(page.getByText("객체 있으나 DB row 없음")).toBeVisible();
    await expect(page.getByRole("button", { name: /선택 항목 영구 삭제/ })).toBeVisible();
    await expect(page.getByText("용량 (capacity)")).toBeVisible();
  });

  test("검증 케이스 탭: registry에서 C1~C17를 동적으로 렌더한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "검증 케이스" }).click();

    await expect(page.getByRole("tab", { name: /C17/ })).toBeVisible();
  });

  test("RustFS 정합성 탭: 정리 대상 선택→typed confirmation→일괄 영구 삭제", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();

    await page.getByLabel(/정리 대상 선택:/).check();
    await page.getByRole("button", { name: /선택 항목 영구 삭제/ }).click();

    const dialog = page.getByRole("dialog", { name: "원천 객체 영구 삭제" });
    await expect(dialog).toBeVisible();
    const exec = dialog.getByRole("button", { name: /영구 삭제 실행/ });
    await expect(exec).toBeDisabled();
    await dialog.getByLabel("hard-delete 확인 문구").fill("HARD-DELETE-SOURCES");
    await expect(exec).toBeEnabled();
    await exec.click();

    // 구조화된 결과 요약(raw JSON 아님)
    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.getByText("영구 삭제")).toBeVisible();
  });
});
