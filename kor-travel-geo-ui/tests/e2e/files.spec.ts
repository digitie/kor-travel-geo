import { expect, test, type Page } from "@playwright/test";

import { ADMIN_PAGES } from "../../lib/admin-pages";

// /admin/files (T-283 파일 관리) mock e2e. 백엔드 admin API를 page.route로 목킹해
// 통합 파일 인벤토리(목록·필터·연결 상세)를 DB 없이 검증한다.

const INVENTORY_PAGE = {
  items: [
    {
      file_kind: "source_group",
      id: "group-1",
      name: "도로명주소 한글 전체분",
      category: "roadname_hangul_full",
      state: "available",
      lifecycle: "serving",
      in_use: true,
      temporary: false,
      size_bytes: 1_073_741_824,
      file_count: 1,
      sha256: "a".repeat(64),
      storage_kind: "rustfs",
      storage_ref: "sources/roadname/archive.zip",
      user_yyyymm: "202605",
      acquired_at: "2026-06-01T09:00:00Z",
      registered_at: "2026-06-01T09:20:00Z",
      last_verified_at: "2026-06-20T01:00:00Z",
      last_loaded_at: "2026-06-18T13:33:00Z",
      last_load_job_id: "job-full-1",
      upload_session_id: "us-1",
      upload_session_state: "registered",
      active_match_set_id: "ms-active",
      match_set_count: 2,
      open_issue_count: 0,
      detail: { validation_state: "passed" }
    },
    {
      file_kind: "artifact",
      id: "art-1",
      name: "kor_travel_geo-20260701.tar.zst",
      category: "db_backup",
      state: "available",
      lifecycle: "available",
      in_use: false,
      temporary: false,
      size_bytes: 87_241_216,
      acquired_at: "2026-07-01T00:00:00Z",
      expires_at: "2026-07-31T00:00:00Z",
      job_id: "job-backup-1",
      match_set_count: 0,
      open_issue_count: 0,
      detail: {}
    },
    {
      file_kind: "orphan_object",
      id: "orphan-1",
      name: "sources/tmp/unknown.zip",
      category: "rustfs_object",
      state: "object_missing_db",
      lifecycle: "orphan",
      in_use: false,
      temporary: true,
      size_bytes: 2_048,
      storage_kind: "rustfs",
      storage_ref: "sources/tmp/unknown.zip",
      acquired_at: "2026-06-30T00:00:00Z",
      match_set_count: 0,
      open_issue_count: 0,
      detail: { severity: "WARN" }
    }
  ],
  summary: {
    total_count: 3,
    total_bytes: 1_160_985_088,
    in_use_count: 1,
    temporary_count: 1,
    open_issue_count: 0,
    by_lifecycle: { serving: 1, available: 1, orphan: 1 },
    by_kind: { source_group: 1, artifact: 1, orphan_object: 1 }
  }
};

const GROUP_DETAIL = {
  item: INVENTORY_PAGE.items[0],
  files: [
    {
      source_file_id: "file-1",
      original_filename: "도로명주소 한글_전체분.zip",
      part_key: "archive",
      state: "available",
      validation_state: "passed",
      size_bytes: 1_073_741_824,
      sha256: "a".repeat(64),
      storage_kind: "rustfs",
      bucket: "ktg-sources",
      object_key: "sources/roadname/archive.zip",
      uploaded_at: "2026-06-01T09:00:00Z",
      last_verified_at: "2026-06-20T01:00:00Z"
    }
  ],
  sessions: [
    {
      source_upload_session_id: "us-1",
      state: "registered",
      created_at: "2026-06-01T08:50:00Z",
      registered_at: "2026-06-01T09:20:00Z"
    }
  ],
  usages: [
    {
      source_match_set_id: "ms-active",
      name: "202605 전국 서빙 세트",
      state: "active",
      role: "build_required",
      last_load_job_id: "job-full-1",
      last_load_job_state: "done",
      last_loaded_at: "2026-06-18T13:33:00Z"
    },
    {
      source_match_set_id: "ms-old",
      name: "202604 이전 세트",
      state: "retired",
      role: "build_required",
      last_loaded_at: "2026-05-18T10:00:00Z"
    }
  ],
  open_issues: []
};

const requestedUrls: string[] = [];

async function mockFilesApi(page: Page): Promise<void> {
  requestedUrls.length = 0;
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ vworldApiKey: "" }) });
  });
  await page.route("**/api/proxy/v1/admin/storage/files**", async (route) => {
    const url = new URL(route.request().url());
    requestedUrls.push(url.pathname + url.search);
    if (url.pathname.includes("/source-groups/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(GROUP_DETAIL) });
      return;
    }
    const temporaryOnly = url.searchParams.get("temporary_only") === "true";
    const body = temporaryOnly
      ? {
          ...INVENTORY_PAGE,
          items: INVENTORY_PAGE.items.filter((item) => item.temporary),
          summary: { ...INVENTORY_PAGE.summary, total_count: 1 }
        }
      : INVENTORY_PAGE;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

test.describe("파일 관리 /admin/files (T-283)", () => {
  test.beforeEach(async ({ page }) => {
    await mockFilesApi(page);
    await page.goto("/admin/files");
    await expect(
      page.getByRole("heading", { name: ADMIN_PAGES.files.title, exact: true })
    ).toBeVisible();
  });

  test("요약 타일과 통합 목록을 렌더한다", async ({ page }) => {
    await expect(page.getByText("전체 파일")).toBeVisible();
    const table = page.getByRole("table", { name: "파일 인벤토리 목록" });
    await expect(table).toBeVisible();
    await expect(table.getByText("도로명주소 한글 전체분")).toBeVisible();
    await expect(table.getByText("kor_travel_geo-20260701.tar.zst")).toBeVisible();
    await expect(table.getByText("서빙 사용 중")).toBeVisible();
    await expect(table.getByText("미등록 객체")).toBeVisible();
    await expect(table.getByText("사용 중")).toBeVisible();
  });

  test("임시/정리 대상 필터가 쿼리로 전달된다", async ({ page }) => {
    await page.getByRole("checkbox", { name: "임시/정리 대상만" }).check();
    await expect
      .poll(() => requestedUrls.some((url) => url.includes("temporary_only=true")))
      .toBe(true);
    const table = page.getByRole("table", { name: "파일 인벤토리 목록" });
    await expect(table.getByText("sources/tmp/unknown.zip")).toBeVisible();
    await expect(table.getByText("도로명주소 한글 전체분")).toHaveCount(0);
  });

  test("행 클릭이 원천 그룹의 연결 상세를 보여 준다", async ({ page }) => {
    await page
      .getByRole("table", { name: "파일 인벤토리 목록" })
      .getByText("도로명주소 한글 전체분")
      .click();
    const dialog = page.getByRole("dialog", { name: "파일 상세" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("매칭 세트 사용처 (2)")).toBeVisible();
    await expect(dialog.getByText("202605 전국 서빙 세트")).toBeVisible();
    await expect(dialog.getByText("활성")).toBeVisible();
    await expect(dialog.getByText("업로드 이력 (1)")).toBeVisible();
    await expect(dialog.getByText("구성 파일 (1)")).toBeVisible();
  });

  test("고아 객체 상세는 정리 안내를 보여 준다", async ({ page }) => {
    await page
      .getByRole("table", { name: "파일 인벤토리 목록" })
      .getByText("sources/tmp/unknown.zip")
      .click();
    const dialog = page.getByRole("dialog", { name: "파일 상세" });
    await expect(dialog.getByText("DB에 등록되지 않은 저장소 객체입니다")).toBeVisible();
    await expect(dialog.getByRole("link", { name: "RustFS 정합성으로 이동" })).toBeVisible();
  });

  test("목록 오류 시 재시도 가능한 경고를 보여 준다", async ({ page }) => {
    await page.route("**/api/proxy/v1/admin/storage/files**", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "mock 500" })
      });
    });
    await page.getByRole("button", { name: "새로고침" }).click();
    await expect(page.getByRole("alert").getByText("파일 목록을 불러오지 못했습니다")).toBeVisible();
    await expect(page.getByRole("button", { name: "다시 시도" })).toBeVisible();
  });
});
