import { expect, type Page, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { loginLiveAdmin, loginLiveAdminPage, proxyGet } from "./_live";

type LoadJob = {
  job_id: string;
  kind: string;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  load_batch_id?: string | null;
  progress: number;
  current_stage?: string | null;
  error_message?: string | null;
  finished_at?: string | null;
  payload_summary?: Record<string, unknown> | null;
};

type MatchSetDetail = {
  match_set: {
    source_match_set_id: string;
    name: string;
    state: string;
  };
};

type DatasetSnapshot = {
  dataset_snapshot_id: string;
  source_set?: {
    rebuild_metadata?: Record<string, unknown>;
  } & Record<string, unknown>;
  row_counts?: Record<string, number>;
};

type ServingRelease = {
  serving_release_id: string;
  dataset_snapshot_id: string;
  state: string;
  release_kind: string;
  activated_by_job_id?: string | null;
  consistency_gate?: Record<string, unknown>;
};

const MATCH_SET_ID = process.env.KTG_LIVE_E2E_REBUILD_MATCH_SET_ID ?? "";
const RUN_CONFIRMATION =
  process.env.KTG_LIVE_E2E_REBUILD_RUN_CONFIRM ??
  process.env.KTG_LIVE_E2E_REBUILD_CONFIRM ??
  "";
const EXISTING_REBUILD_JOB_ID = process.env.KTG_LIVE_E2E_REBUILD_EXISTING_JOB_ID ?? "";
const FORCE_PROMOTION = boolEnv("KTG_LIVE_E2E_REBUILD_FORCE_PROMOTION");
const FORCE_PROMOTION_REASON =
  process.env.KTG_LIVE_E2E_REBUILD_FORCE_PROMOTION_REASON ??
  "T-183 live UI e2e forced promotion for known source-quality consistency ERROR";
const ADMIN_ACTOR = process.env.KTG_LIVE_E2E_ADMIN_ACTOR ?? "";
const ADMIN_ROLES = new Set(
  (process.env.KTG_LIVE_E2E_ADMIN_ROLES ?? "")
    .split(",")
    .map((role) => role.trim())
    .filter(Boolean)
);
const TIMEOUT_MS = positiveMs("KTG_LIVE_E2E_REBUILD_TIMEOUT_MS", 24 * 60 * 60 * 1000);
const POLL_MS = positiveMs("KTG_LIVE_E2E_REBUILD_POLL_MS", 10_000);

test.describe("LIVE source-files rebuild-db through Admin UI (T-183)", () => {
  test.beforeEach(async ({ page, request }) => {
    test.skip(
      !process.env.LIVE_E2E ||
        process.env.KTG_LIVE_E2E_ADMIN_PROXY !== "1" ||
        !ADMIN_ACTOR ||
        !ADMIN_ROLES.has("source_file_viewer") ||
        !ADMIN_ROLES.has("rebuild_operator") ||
        (FORCE_PROMOTION && !ADMIN_ROLES.has("destructive_admin")) ||
        !MATCH_SET_ID ||
        !RUN_CONFIRMATION,
      "Destructive live rebuild — requires LIVE_E2E=1, admin proxy actor/roles, match set id, run confirmation, and destructive_admin when force promotion is enabled"
    );
    await loginLiveAdmin(request);
    await loginLiveAdminPage(page, "/admin/source-files");
  });

  test("starts rebuild-db from the UI and waits for post-load serving evidence", async ({
    page,
    request
  }) => {
    test.setTimeout(TIMEOUT_MS + 60_000);

    const ready = await proxyGet(request, "v1/readyz");
    expect(ready.status()).toBe(200);
    const readyBody = (await ready.json()) as {
      components?: { database?: { detail?: { current_database?: string } } };
    };
    const database = readyBody.components?.database?.detail?.current_database ?? "";
    expect(RUN_CONFIRMATION).toBe(`RUN-T183-UI-REBUILD ${database}`);

    const detailRes = await proxyGet(request, `v1/admin/source-match-sets/${MATCH_SET_ID}`);
    expect(detailRes.status()).toBe(200);
    const detail = (await detailRes.json()) as MatchSetDetail;
    expect(detail.match_set.source_match_set_id).toBe(MATCH_SET_ID);

    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();
    await page.getByTestId(`source-match-set-${MATCH_SET_ID}`).click();

    const adoptedExistingJob = Boolean(EXISTING_REBUILD_JOB_ID);
    const jobId =
      EXISTING_REBUILD_JOB_ID ||
      (await startRebuildFromUi(page, MATCH_SET_ID, {
        forcePromotion: FORCE_PROMOTION,
        reason: FORCE_PROMOTION_REASON
      }));

    const controlJob = await waitForJobDone(request, jobId);
    expect(controlJob.state).toBe("done");
    expect(controlJob.kind).toBe("source_rebuild_db");
    expectJobPayload(controlJob, {
      sourceMatchSetId: MATCH_SET_ID,
      forcePromotion: FORCE_PROMOTION
    });
    expect(typeof controlJob.load_batch_id).toBe("string");
    const loadBatchId = controlJob.load_batch_id!;
    if (!adoptedExistingJob) {
      await expect(page.getByTestId("rebuild-load-batch-id")).toHaveText(loadBatchId, {
        timeout: 30_000
      });
      await expect(page.getByTestId("rebuild-load-batch-status")).toBeVisible();
    }

    const batchJob = await waitForJobDone(request, loadBatchId);
    expect(batchJob.state).toBe("done");
    expect(batchJob.kind).toBe("full_load_batch");
    expectJobPayload(batchJob, {
      sourceMatchSetId: MATCH_SET_ID,
      forcePromotion: FORCE_PROMOTION
    });

    const { release, snapshot } = await waitForServingEvidence(request, loadBatchId);
    const rowCounts = snapshot.row_counts ?? {};
    expect(rowCounts.mv_geocode_target).toBeGreaterThan(0);
    expect(rowCounts.mv_geocode_text_search).toBeGreaterThan(0);
    expect(rowCounts.tl_juso_text).toBeGreaterThan(0);
    expect(release.state).toBe("active");
    expect(release.release_kind).toBe("full_load");
    expect(release.dataset_snapshot_id).toBe(snapshot.dataset_snapshot_id);
    expect(snapshot.source_set?.load_batch_id).toBe(loadBatchId);
    if (FORCE_PROMOTION) {
      const rebuildMetadata = snapshot.source_set?.rebuild_metadata ?? {};
      expect(rebuildMetadata.forced_promotion).toBe(true);
      expect(rebuildMetadata.consistency_severity).toBe("ERROR");
      expect(rebuildMetadata.forced_promotion_actor).toBe(ADMIN_ACTOR);
      expect(rebuildMetadata.forced_promotion_reason).toBe(FORCE_PROMOTION_REASON);
      expect(release.consistency_gate?.severity_max).toBe("ERROR");
    }

    writeArtifact({
      database,
      source_match_set_id: MATCH_SET_ID,
      force_promotion: FORCE_PROMOTION,
      control_job: controlJob,
      batch_job: batchJob,
      row_counts: rowCounts,
      active_release: release,
      dataset_snapshot: snapshot
    });
  });
});

async function startRebuildFromUi(
  page: Page,
  matchSetId: string,
  options: { forcePromotion: boolean; reason: string }
): Promise<string> {
  const form = page.locator(".rebuild-form");
  if (options.forcePromotion) {
    await form.getByRole("checkbox", { name: /force_promotion/ }).check();
    await form.getByLabel("사유", { exact: true }).fill(options.reason);
    await form
      .getByLabel("rebuild 강제 승급 확인 문구")
      .fill(`REBUILD-PROMOTE ${matchSetId}`);
  }
  const rebuildRequest = page.waitForRequest(
    (req) => req.url().endsWith(`/${matchSetId}/rebuild-db`) && req.method() === "POST"
  );
  const rebuildResponse = page.waitForResponse(
    (res) => res.url().endsWith(`/${matchSetId}/rebuild-db`) && res.request().method() === "POST"
  );
  await form.getByRole("button", { name: "rebuild-db 실행" }).click();
  const requestBody = (await rebuildRequest).postDataJSON() as {
    force_promotion?: boolean;
    reason?: string | null;
    typed_confirmation?: string | null;
  };
  expect(requestBody.force_promotion).toBe(options.forcePromotion);
  if (options.forcePromotion) {
    expect(requestBody.reason).toBe(options.reason);
    expect(requestBody.typed_confirmation).toBe(`REBUILD-PROMOTE ${matchSetId}`);
  }
  const response = await rebuildResponse;
  const responseStatus = response.status();
  const responseBody = responseStatus === 200 ? "" : await response.text();
  expect(responseStatus, responseBody).toBe(200);
  const rebuild = (await response.json()) as {
    enqueued?: boolean;
    forced_promotion?: boolean;
    job_id?: string;
  };
  expect(rebuild.enqueued).toBe(true);
  expect(rebuild.forced_promotion).toBe(options.forcePromotion);
  expect(typeof rebuild.job_id).toBe("string");
  const jobId = rebuild.job_id!;

  await expect(page.getByRole("heading", { name: "rebuild-db 진행 상태" })).toBeVisible();
  await expect(page.getByTestId("rebuild-control-job-id")).toHaveText(jobId);
  return jobId;
}

function boolEnv(name: string): boolean {
  const raw = process.env[name];
  if (!raw) {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

async function waitForJobDone(
  request: Parameters<typeof proxyGet>[0],
  jobId: string
): Promise<LoadJob> {
  const deadline = Date.now() + TIMEOUT_MS;
  let last: LoadJob | null = null;
  while (Date.now() < deadline) {
    const res = await proxyGet(request, `v1/admin/jobs/${jobId}`);
    expect(res.status()).toBe(200);
    last = (await res.json()) as LoadJob;
    if (last.state === "done") {
      return last;
    }
    if (last.state === "failed" || last.state === "cancelled") {
      throw new Error(`rebuild job ${last.state}: ${last.error_message ?? ""}`);
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
  throw new Error(`Timed out waiting for rebuild job ${jobId}; last=${JSON.stringify(last)}`);
}

function expectJobPayload(
  job: LoadJob,
  expected: { sourceMatchSetId: string; forcePromotion: boolean }
): void {
  const summary = job.payload_summary ?? {};
  expect(summary.source_match_set_id).toBe(expected.sourceMatchSetId);
  if (expected.forcePromotion) {
    expect(Boolean(summary.force_promotion ?? summary.forced_promotion)).toBe(true);
  }
}

async function waitForServingEvidence(
  request: Parameters<typeof proxyGet>[0],
  jobId: string
): Promise<{ release: ServingRelease; snapshot: DatasetSnapshot }> {
  const deadline = Date.now() + TIMEOUT_MS;
  let last: unknown = null;
  while (Date.now() < deadline) {
    const releases = await proxyGet(request, "v1/admin/ops/releases", { limit: 200 });
    expect(releases.status()).toBe(200);
    const releaseRows = (await releases.json()) as ServingRelease[];
    const release = releaseRows.find(
      (row) => row.consistency_gate?.load_batch_id === jobId
    );

    if (release) {
      const snapshots = await proxyGet(request, "v1/admin/ops/snapshots", { limit: 200 });
      expect(snapshots.status()).toBe(200);
      const snapshotRows = (await snapshots.json()) as DatasetSnapshot[];
      const snapshot = snapshotRows.find(
        (row) => row.dataset_snapshot_id === release.dataset_snapshot_id
      );
      if (snapshot?.row_counts) {
        return { release, snapshot };
      }
      last = { release, snapshots: snapshotRows };
    } else {
      last = { releases: releaseRows };
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
  throw new Error(`Timed out waiting for serving release evidence; last=${JSON.stringify(last)}`);
}

function positiveMs(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) {
    return fallback;
  }
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive finite millisecond value`);
  }
  return parsed;
}

function writeArtifact(payload: unknown): void {
  const dir = process.env.KTG_LIVE_E2E_ARTIFACT_DIR;
  if (!dir) {
    return;
  }
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "t183-ui-rebuild-live.json"),
    JSON.stringify(payload, null, 2) + "\n",
    "utf-8"
  );
}
