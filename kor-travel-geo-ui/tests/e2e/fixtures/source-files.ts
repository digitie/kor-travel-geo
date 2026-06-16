import { type Page } from "@playwright/test";

/**
 * Deterministic fake-API harness for `/admin/source-files` e2e (T-225).
 *
 * Centralizes the source-files admin contract (categories, upload-session state machine +
 * multipart, match sets, reconcile, capacity, consistency, config) behind one configurable
 * `page.route` installer so the staged e2e (T-259~T-263) don't each re-implement mocks and
 * don't depend on a live backend. Knobs: per-fixture overrides, error injection, SSE frame
 * control (incl. disconnect), and a custom-route escape hatch.
 *
 * Defaults reproduce the T-223 `source-files.spec.ts` fixtures so that spec consumes the
 * harness with no behavior change.
 */

// SSE `source_upload.progress` payload (mirrors lib/source-files SourceUploadProgressEvent;
// kept local so e2e specs avoid the @/ alias).
export type ProgressEvent = {
  event: "source_upload.progress";
  upload_session_id: string;
  state: string;
  stage?: string | null;
  progress?: number | null;
  current_item?: string | null;
  uploaded_bytes?: number;
  total_bytes?: number;
  message?: string | null;
  log_tail?: string | null;
};

type Json = Record<string, unknown>;

// ---------------------------------------------------------------------------
// Fixture factories (sensible defaults + shallow overrides)
// ---------------------------------------------------------------------------

export function makeCategoryCatalog(extra: Json[] = []): Json {
  return {
    categories: [
      {
        category: "roadname_hangul_full",
        label: "도로명주소 한글 전체분",
        role: "build_required",
        default_role: "build_required",
        serving_usage: "serving_core",
        group_kind: "single_file",
        optional: false,
        expected_member_kinds: ["juso"]
      },
      {
        category: "epost_pobox_full",
        label: "epost 사서함",
        role: "enrichment_candidate",
        default_role: "enrichment_candidate",
        serving_usage: "separate_feature_candidate",
        group_kind: "single_file",
        optional: true,
        expected_member_kinds: []
      },
      ...extra
    ]
  };
}

export function makeFileSlot(overrides: Json = {}): Json {
  return {
    slot: "archive",
    part_key: "archive",
    part_kind: "single",
    part_label: null,
    required: true,
    uploaded: false,
    received_bytes: 0,
    object_key: null,
    object_etag: null,
    multipart_upload_id: null,
    sha256: null,
    ...overrides
  };
}

export function makeUploadSession(overrides: Json = {}): Json {
  const id = (overrides.upload_session_id as string) ?? "us_default";
  return {
    upload_session_id: id,
    source_file_group_id: `grp_${id}`,
    category: "roadname_hangul_full",
    display_name: "도로명주소 한글 전체분 202603",
    state: "created",
    registration_state: "not_registered",
    group_kind: "single_file",
    storage_kind: "rustfs",
    upload_strategy: "multipart",
    user_yyyymm: "202603",
    expected_file_count: 1,
    uploaded_file_count: 0,
    max_bytes: 5_000_000_000,
    part_size_bytes: 8 * 1024 * 1024,
    file_slots: [makeFileSlot()],
    metadata: {},
    created_at: "2026-06-16T00:00:00Z",
    updated_at: "2026-06-16T00:00:00Z",
    ...overrides
  };
}

export function makeProgressEvent(sessionId: string, overrides: Partial<ProgressEvent> = {}): ProgressEvent {
  return {
    event: "source_upload.progress",
    upload_session_id: sessionId,
    state: "uploading",
    stage: "multipart",
    progress: 0.5,
    uploaded_bytes: 50,
    total_bytes: 100,
    ...overrides
  };
}

export function makeMatchSets(): Json[] {
  return [
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
}

export function makeMatchSetDetail(matchSet?: Json): Json {
  const set = matchSet ?? makeMatchSets()[0];
  return {
    match_set: set,
    items: [
      {
        source_match_set_item_id: "item_1",
        source_match_set_id: set.source_match_set_id,
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
}

export function makeReconcileRuns(): Json[] {
  return [
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
}

export function makeReconcileItems(): Json {
  return {
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
}

export function makeCapacity(): Json {
  return {
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
}

export function makeCaseDefinitions(count = 17): Json[] {
  return Array.from({ length: count }, (_, index) => ({
    code: `C${index + 1}`,
    name: `${index + 1}번 케이스`,
    compares: "원천 비교",
    abnormal_criteria: "임계값 초과",
    evidence: ["증거"],
    likely_causes: ["원인"],
    decision_guide: "지도 확인",
    threshold: "WARN"
  }));
}

export function makeConsistencyReports(): Json[] {
  return [
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
}

// ---------------------------------------------------------------------------
// Mock installer
// ---------------------------------------------------------------------------

/** Inject an error for endpoints whose pathname matches `path` (string=substring, or RegExp). */
export type ErrorRule = { path: string | RegExp; method?: string; status: number; body?: string };

/** SSE plan for an upload session's `/events` stream. `status>=400` simulates a dropped stream. */
export type SsePlan = { frames?: ProgressEvent[]; status?: number };

export type RouteContext = {
  pathname: string;
  method: string;
  url: URL;
  route: import("@playwright/test").Route;
};

export type SourceFilesMockOptions = {
  vworldApiKey?: string;
  catalog?: Json;
  uploadSessions?: Json[];
  matchSets?: Json[];
  matchSetDetail?: Json;
  capacity?: Json;
  reconcileRuns?: Json[];
  reconcileItems?: Json;
  consistencyReports?: Json[];
  caseDefinitions?: Json[];
  releases?: Json[];
  snapshots?: Json[];
  /** Error injection, evaluated in order before normal routing. */
  errors?: ErrorRule[];
  /** Per-session SSE plan; default is an empty (immediately-closed) stream. */
  sse?: (sessionId: string) => SsePlan;
  /** Override action-endpoint JSON by pathname suffix (e.g. "/register", "/activate"). */
  responses?: Record<string, unknown>;
  /** Escape hatch: return true if the route was fully handled. */
  onRoute?: (ctx: RouteContext) => boolean | Promise<boolean>;
};

const json = (body: unknown) => ({
  contentType: "application/json",
  body: JSON.stringify(body)
});

function sseBody(frames: ProgressEvent[]): string {
  return frames
    .map((frame) => `event: source_upload.progress\ndata: ${JSON.stringify(frame)}\n\n`)
    .join("");
}

function matchError(rules: ErrorRule[] | undefined, pathname: string, method: string): ErrorRule | null {
  if (!rules) return null;
  for (const rule of rules) {
    if (rule.method && rule.method.toUpperCase() !== method) continue;
    const hit = typeof rule.path === "string" ? pathname.includes(rule.path) : rule.path.test(pathname);
    if (hit) return rule;
  }
  return null;
}

function suffixOverride(responses: Record<string, unknown> | undefined, pathname: string): unknown {
  if (!responses) return undefined;
  for (const [suffix, body] of Object.entries(responses)) {
    if (pathname.endsWith(suffix)) return body;
  }
  return undefined;
}

const UNHANDLED = Symbol("unhandled");

function resolveBody(pathname: string, method: string, url: URL, opts: Required_<SourceFilesMockOptions>): unknown {
  const override = suffixOverride(opts.responses, pathname);
  if (override !== undefined) return override;

  // --- upload sessions + multipart ---
  if (/\/upload-sessions\/[^/]+\/files\/[^/]+\/multipart\/complete$/.test(pathname)) {
    return makeUploadSession({ upload_session_id: sessionIdFromMultipart(pathname), state: "uploaded_to_temp", uploaded_file_count: 1 });
  }
  if (/\/upload-sessions\/[^/]+\/files\/[^/]+\/multipart\/\d+$/.test(pathname) && method === "PUT") {
    const partNumber = Number(pathname.split("/").pop());
    return { part_number: partNumber, part_etag: `etag-${partNumber}` };
  }
  if (/\/upload-sessions\/[^/]+\/files\/[^/]+\/multipart$/.test(pathname) && method === "POST") {
    return { multipart_upload_id: "mp-1", part_size_bytes: 8 * 1024 * 1024 };
  }
  if (/\/upload-sessions\/[^/]+\/register$/.test(pathname) && method === "POST") {
    return makeUploadSession({ upload_session_id: sessionIdFromRegister(pathname), state: "registered", registration_state: "registered" });
  }
  if (pathname.endsWith("/upload-sessions") && method === "POST") {
    return makeUploadSession({ upload_session_id: "us_new", state: "created" });
  }
  if (/\/upload-sessions\/[^/]+$/.test(pathname) && method === "GET") {
    const id = pathname.split("/").pop() as string;
    return opts.uploadSessions.find((s) => s.upload_session_id === id) ?? makeUploadSession({ upload_session_id: id });
  }
  if (pathname.endsWith("/upload-sessions") && method === "GET") {
    const state = url.searchParams.get("state");
    return state ? opts.uploadSessions.filter((s) => s.state === state) : opts.uploadSessions;
  }
  if (pathname.endsWith("/epost-fetch")) {
    return { upload_session_id: "us_epost", state: "uploaded_to_temp", message: "epost fetched" };
  }

  // --- match sets ---
  if (/\/source-match-sets\/[^/]+\/(validate|activate|retire|rebuild-db|run-validation)$/.test(pathname)) {
    return { ...(opts.matchSetDetail as Json).match_set as Json, ok: true };
  }
  if (/\/source-match-sets\/[^/]+$/.test(pathname)) {
    return opts.matchSetDetail;
  }
  if (pathname.includes("/source-match-sets")) {
    return opts.matchSets;
  }

  // --- source-file groups ---
  if (/\/source-file-groups\/[^/]+\/(soft-delete|restore|relink|validate)$/.test(pathname)) {
    return { ok: true };
  }

  // --- reconcile ---
  if (pathname.includes("/reconcile/items/") && pathname.endsWith("/resolve")) {
    return { resolved: true };
  }
  if (pathname.includes("/reconcile/") && pathname.includes("/items")) {
    return opts.reconcileItems;
  }
  if (pathname.includes("/reconcile")) {
    return opts.reconcileRuns;
  }
  if (pathname.endsWith("/bulk-hard-delete")) {
    return {
      requested_count: 1,
      hard_deleted_count: 1,
      delete_failed_count: 0,
      skipped_count: 0,
      results: [{ object_key: "source/electronic_map_full/orphan-36.zip", outcome: "hard_deleted" }],
      affected_match_set_ids: []
    };
  }

  // --- catalog / capacity ---
  if (pathname.endsWith("/source-file-categories")) return opts.catalog;
  if (pathname.endsWith("/source-files/capacity")) return opts.capacity;

  // --- consistency + config ---
  if (pathname.includes("/consistency/case-definitions")) return opts.caseDefinitions;
  if (pathname.endsWith("/consistency")) return opts.consistencyReports;
  if (pathname.includes("/consistency/")) return { ...opts.consistencyReports[0], cases: [] };
  if (pathname.includes("/ops/releases")) return opts.releases;
  if (pathname.includes("/ops/snapshots")) return opts.snapshots;

  return UNHANDLED;
}

function sessionIdFromEvents(pathname: string): string {
  const m = pathname.match(/\/upload-sessions\/([^/]+)\/events$/);
  return m ? m[1] : "";
}
function sessionIdFromRegister(pathname: string): string {
  const m = pathname.match(/\/upload-sessions\/([^/]+)\/register$/);
  return m ? m[1] : "";
}
function sessionIdFromMultipart(pathname: string): string {
  const m = pathname.match(/\/upload-sessions\/([^/]+)\/files\//);
  return m ? m[1] : "";
}

// Required<T> keeps optional callbacks (errors/sse/responses/onRoute/uploadSessions) optional.
type Required_<T> = T & {
  vworldApiKey: string;
  catalog: Json;
  uploadSessions: Json[];
  matchSets: Json[];
  matchSetDetail: Json;
  capacity: Json;
  reconcileRuns: Json[];
  reconcileItems: Json;
  consistencyReports: Json[];
  caseDefinitions: Json[];
  releases: Json[];
  snapshots: Json[];
};

function withDefaults(options: SourceFilesMockOptions): Required_<SourceFilesMockOptions> {
  return {
    ...options,
    vworldApiKey: options.vworldApiKey ?? "",
    catalog: options.catalog ?? makeCategoryCatalog(),
    uploadSessions: options.uploadSessions ?? [],
    matchSets: options.matchSets ?? makeMatchSets(),
    matchSetDetail: options.matchSetDetail ?? makeMatchSetDetail(),
    capacity: options.capacity ?? makeCapacity(),
    reconcileRuns: options.reconcileRuns ?? makeReconcileRuns(),
    reconcileItems: options.reconcileItems ?? makeReconcileItems(),
    consistencyReports: options.consistencyReports ?? makeConsistencyReports(),
    caseDefinitions: options.caseDefinitions ?? makeCaseDefinitions(),
    releases: options.releases ?? [],
    snapshots: options.snapshots ?? []
  };
}

/**
 * Install the source-files fake API on `page`. Routes `/api/runtime-config` and every
 * `/api/proxy/v1/admin/**` source-files/consistency/ops endpoint to deterministic fixtures.
 */
export async function installSourceFilesMock(
  page: Page,
  options: SourceFilesMockOptions = {}
): Promise<void> {
  const opts = withDefaults(options);

  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(json({ vworldApiKey: opts.vworldApiKey }));
  });

  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    if (opts.onRoute && (await opts.onRoute({ pathname, method, url, route }))) return;

    const err = matchError(opts.errors, pathname, method);
    if (err) {
      await route.fulfill({
        status: err.status,
        contentType: "application/json",
        body: err.body ?? JSON.stringify({ detail: `mock ${err.status}` })
      });
      return;
    }

    if (pathname.endsWith("/events")) {
      const plan = opts.sse?.(sessionIdFromEvents(pathname)) ?? { frames: [] };
      if (plan.status && plan.status >= 400) {
        await route.fulfill({ status: plan.status, contentType: "text/event-stream", body: "" });
        return;
      }
      await route.fulfill({ contentType: "text/event-stream", body: sseBody(plan.frames ?? []) });
      return;
    }

    const body = resolveBody(pathname, method, url, opts);
    if (body === UNHANDLED) {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill(json(body));
  });
}
