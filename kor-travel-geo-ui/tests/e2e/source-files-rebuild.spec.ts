import { expect, test } from "@playwright/test";
import { installSourceFilesMock } from "./fixtures/source-files";

// T-263 단계별 e2e: DB 입력(rebuild-db). 매칭 세트 세부의 DB 재구성 흐름 —
// rebuild-db enqueue·force_promotion typed confirmation·실패 경로 — 를 T-225 공용 하네스로
// 백엔드 없이 고정한다. (enqueue된 load job의 라이브 진행률(SSE/polling)은 /admin/load 표면이라
// 여기서는 enqueue 응답(job_id/enqueued)까지 검증한다.) (의존: T-225)

const REBUILD_FORM = ".rebuild-form";

test.describe("DB 입력(rebuild-db) /admin/source-files (T-263)", () => {
  test("force_promotion: 정확한 확인 문구 전에는 rebuild-db가 차단된다", async ({ page }) => {
    await installSourceFilesMock(page); // 기본 ms_active 자동 선택
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const form = page.locator(REBUILD_FORM);
    const submit = form.getByRole("button", { name: "rebuild-db 실행" });
    // force 미체크면 확인 문구 없이도 실행 가능.
    await expect(submit).toBeEnabled();

    await form.getByRole("checkbox").check();
    // force 체크 → 확인 문구 입력 전 차단.
    await expect(submit).toBeDisabled();

    const confirm = form.getByLabel("rebuild 강제 승급 확인 문구");
    await confirm.fill("REBUILD-PROMOTE wrong");
    await expect(submit).toBeDisabled();
    await expect(form.getByText("확인 문구가 일치해야 합니다.")).toBeVisible();

    await confirm.fill("REBUILD-PROMOTE ms_active");
    await expect(submit).toBeEnabled();
  });

  test("enqueue: rebuild-db 실행이 job enqueue 결과를 노출한다", async ({ page }) => {
    await installSourceFilesMock(page, {
      responses: {
        "/rebuild-db": {
          source_match_set_id: "ms_active",
          enqueued: true,
          job_id: "job-rebuild-1",
          load_batch_id: "batch-1",
          forced_promotion: false,
          integrity_gate_ok: true,
          affected_match_set_ids: ["ms_active"],
          failed_group_ids: []
        }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    await page.locator(REBUILD_FORM).getByRole("button", { name: "rebuild-db 실행" }).click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"enqueued": true');
    await expect(result.locator("pre")).toContainText('"job_id": "job-rebuild-1"');
  });

  test("force_promotion enqueue: 확인 문구 후 force_promotion 본문으로 제출된다", async ({
    page
  }) => {
    await installSourceFilesMock(page, {
      responses: {
        "/rebuild-db": {
          source_match_set_id: "ms_active",
          enqueued: true,
          job_id: "job-rebuild-2",
          forced_promotion: true,
          integrity_gate_ok: false,
          affected_match_set_ids: ["ms_active"],
          failed_group_ids: []
        }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const form = page.locator(REBUILD_FORM);
    await form.getByRole("checkbox").check();
    await form.getByLabel("rebuild 강제 승급 확인 문구").fill("REBUILD-PROMOTE ms_active");

    const rebuildRequest = page.waitForRequest(
      (req) => req.url().endsWith("/rebuild-db") && req.method() === "POST"
    );
    await form.getByRole("button", { name: "rebuild-db 실행" }).click();
    const body = (await rebuildRequest).postDataJSON();
    expect(body.force_promotion).toBe(true);
    expect(body.typed_confirmation).toBe("REBUILD-PROMOTE ms_active");

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"forced_promotion": true');
  });

  test("실패 경로: rebuild-db 오류가 최근 결과에 노출된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      errors: [{ path: "/rebuild-db", method: "POST", status: 500, body: "rebuild-db 실패 (mock 500)" }]
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    await page.locator(REBUILD_FORM).getByRole("button", { name: "rebuild-db 실행" }).click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText("mock 500");
  });

  test("preflight 체크리스트 + 위험작업 미리보기를 노출한다 (T-226)", async ({ page }) => {
    await installSourceFilesMock(page); // 기본 detail: integrity_alert=true, item 1개(그룹 연결됨)
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const form = page.locator(REBUILD_FORM);
    await expect(form.getByText("사전 점검", { exact: true })).toBeVisible();
    await expect(form.getByText("무결성 경보:", { exact: false })).toBeVisible();
    // 기본 세트는 integrity_alert=true → 무결성 항목이 '차단'.
    await expect(form.getByText("차단", { exact: true }).first()).toBeVisible();
    // 필요 역할 안내(기본: rebuild_operator).
    await expect(form.getByText(/필요 역할/)).toContainText("rebuild_operator");

    // force 체크 시 위험작업 미리보기 + destructive_admin 역할 안내가 추가된다.
    await form.getByRole("checkbox").check();
    await expect(form.getByText("위험작업 미리보기")).toBeVisible();
    await expect(form.getByText(/serving DB를 재구성/)).toBeVisible();
    await expect(form.getByText(/필요 역할/)).toContainText("destructive_admin");
  });
});
