import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourceFilesPanel } from "@/components/admin/source-files/SourceFilesPanel";

const apiMocks = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }
  return {
    ApiError: FakeApiError,
    postJson: vi.fn(),
    requestJson: vi.fn()
  };
});

const FakeApiError = apiMocks.ApiError;

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  ApiError: apiMocks.ApiError,
  backendPath: (path: string) =>
    path.startsWith("/v1") || path.startsWith("/v2") ? path : `/v1${path}`,
  postJson: apiMocks.postJson,
  requestJson: apiMocks.requestJson
}));

const CATEGORY_CATALOG = {
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

const RESUMABLE_SESSION = {
  upload_session_id: "us_open_1",
  category: "roadname_hangul_full",
  user_yyyymm: "202603",
  state: "uploading",
  registration_state: "not_registered",
  group_kind: "single_file",
  uploaded_file_count: 0,
  expected_file_count: 1,
  max_bytes: 1024,
  part_size_bytes: 512,
  expected: 1,
  file_slots: [],
  source_file_group_id: "grp_1",
  created_at: "2026-06-10T00:00:00Z",
  updated_at: "2026-06-10T00:00:00Z",
  display_name: "x",
  storage_kind: "rustfs",
  upload_strategy: "multipart",
  registration_deadline_at: null
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
    mismatch_count: 2,
    resolved_count: 0,
    rehashed_objects: 0,
    skipped_rehash_objects: 0,
    started_at: "2026-06-13T00:00:00Z"
  }
];

const RECONCILE_ITEMS = {
  items: [
    {
      source_storage_reconcile_item_id: "ri_1",
      source_storage_reconcile_run_id: "rec_1",
      issue_type: "hash_mismatch",
      severity: "error",
      state: "open"
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

const CASE_DEFINITIONS = Array.from({ length: 12 }, (_, index) => ({
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

function mockApi() {
  apiMocks.requestJson.mockImplementation(async (path: string) => {
    if (path === "/admin/source-file-categories") return CATEGORY_CATALOG;
    if (path.startsWith("/admin/source-files/upload-sessions")) return [RESUMABLE_SESSION];
    if (path.startsWith("/admin/source-match-sets/")) return MATCH_SET_DETAIL;
    if (path.startsWith("/admin/source-match-sets")) return MATCH_SETS;
    if (path.startsWith("/admin/source-files/reconcile/") && path.includes("/items"))
      return RECONCILE_ITEMS;
    if (path.startsWith("/admin/source-files/reconcile")) return RECONCILE_RUNS;
    if (path === "/admin/source-files/capacity") return CAPACITY;
    if (path === "/admin/consistency/case-definitions") return CASE_DEFINITIONS;
    if (path === "/admin/consistency") return CONSISTENCY_REPORTS;
    if (path.startsWith("/admin/consistency/"))
      return {
        ...CONSISTENCY_REPORTS[0],
        cases: CASE_DEFINITIONS.map((def, index) => ({
          code: def.code,
          name: def.name,
          severity: index === 0 ? "WARN" : "OK",
          count: index + 1
        }))
      };
    if (path.startsWith("/admin/ops/releases")) return [];
    if (path.startsWith("/admin/ops/snapshots")) return [];
    throw new Error(`unhandled path: ${path}`);
  });
  apiMocks.postJson.mockResolvedValue({ ok: true });
}

function renderPanel(initialTab?: Parameters<typeof SourceFilesPanel>[0]["initialTab"]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SourceFilesPanel initialTab={initialTab} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMocks.postJson.mockReset();
  apiMocks.requestJson.mockReset();
  mockApi();
});

describe("SourceFilesPanel", () => {
  it("5개 기능 탭 + 검증 케이스 탭을 렌더한다", () => {
    renderPanel();
    const tabList = screen.getByRole("tablist", { name: "원천 파일 관리 탭" });
    const tabs = within(tabList).getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "업로드",
      "목록",
      "매칭 세트",
      "RustFS 정합성",
      "현재 구성",
      "검증 케이스"
    ]);
  });

  it("업로드 탭에 카테고리 카드와 재개 가능한 세션을 표시한다", async () => {
    renderPanel("upload");
    await screen.findByText("도로명주소 한글 전체분");
    // epost 카드는 server-fetch(받기) 버튼을 비활성으로 렌더한다 (T-207 대기).
    const epostButton = await screen.findByRole("button", { name: /받기 \(T-207 대기\)/ });
    expect(epostButton).toBeDisabled();
    // 재개 가능한 업로드 목록
    expect(await screen.findByText("재개 가능한 업로드")).toBeInTheDocument();
  });

  it("업로드 409 응답 시 중복 세션 다이얼로그를 띄운다", async () => {
    renderPanel("upload");
    await screen.findByText("도로명주소 한글 전체분");

    apiMocks.postJson.mockImplementationOnce(async () => {
      throw new FakeApiError(
        409,
        JSON.stringify({
          detail: {
            upload_session_id: "us_dupe",
            state: "uploading",
            uploaded_file_count: 0,
            expected_file_count: 1
          }
        })
      );
    });

    // 카드에서 파일 선택 후 업로드 → 409 → 다이얼로그
    const card = screen.getByText("도로명주소 한글 전체분").closest(".source-card") as HTMLElement;
    const fileInput = within(card).getByLabelText(/파일 선택/) as HTMLInputElement;
    const file = new File(["data"], "juso.zip", { type: "application/zip" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(within(card).getByRole("button", { name: "업로드" }));

    const dialog = await screen.findByRole("dialog", { name: "중복 업로드 세션" });
    expect(within(dialog).getByText("us_dupe")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "기존 세션 재개" })).toBeInTheDocument();
  });

  it("매칭 세트 탭에서 integrity_alert를 표시한다", async () => {
    renderPanel("match");
    await screen.findByText("활성 세트");
    expect(screen.getAllByText(/무결성 경보/).length).toBeGreaterThan(0);
    // 세부 패널(rebuild form)이 렌더될 때까지 대기
    const forceCheckbox = await screen.findByRole("checkbox", {
      name: /consistency ERROR 강제 승급/
    });
    // rebuild-db 강제 승급 체크 시 typed-confirmation 입력이 나타난다
    fireEvent.click(forceCheckbox);
    expect(
      await screen.findByLabelText("rebuild 강제 승급 확인 문구")
    ).toBeInTheDocument();
  });

  it("목록 탭 상단에 용량/이슈 요약 카드를 렌더한다", async () => {
    renderPanel("list");
    const summary = (await screen.findByText("용량 / 이슈 요약")).closest(
      ".panel"
    ) as HTMLElement;
    // 30일 증가량 (512 B) + 미등록(1024 B = 1.0 KB) + 미해결 이슈(open 1건, error 1건)
    expect(await within(summary).findByText("최근 30일 증가")).toBeInTheDocument();
    expect(within(summary).getByText("512 B")).toBeInTheDocument();
    expect(within(summary).getByText("1.0 KB")).toBeInTheDocument();
    const openDt = within(summary).getByText("미해결 이슈");
    const openDd = openDt.parentElement?.querySelector("dd");
    await waitFor(() => expect(openDd).toHaveTextContent("1"));
  });

  it("RustFS 정합성 탭에 실행/이슈/용량을 표시한다", async () => {
    renderPanel("reconcile");
    await screen.findByText("정합성 실행 (RustFS ⟷ DB)");
    // 12 issue_type 라벨 중 hash_mismatch 매핑이 나타난다
    expect(await screen.findByText("해시 불일치")).toBeInTheDocument();
    // capacity panel
    expect(await screen.findByText("용량 (capacity)")).toBeInTheDocument();
  });

  it("현재 구성 탭에서 active match set이 없으면 알수없음을 표시한다", async () => {
    apiMocks.requestJson.mockImplementation(async (path: string) => {
      if (path.startsWith("/admin/source-match-sets")) return [];
      if (path.startsWith("/admin/ops/releases")) return [];
      if (path.startsWith("/admin/ops/snapshots")) return [];
      throw new Error(`unhandled: ${path}`);
    });
    renderPanel("current");
    expect(
      await screen.findByText(/현재 DB를 만든 원천 매칭 정보: 알수없음/)
    ).toBeInTheDocument();
  });

  it("검증 케이스 탭은 registry에서 C1~C12를 동적으로 렌더한다", async () => {
    renderPanel("cases");
    // registry case-definitions 쿼리가 해소되면 탭이 나타난다
    await screen.findByRole("tab", { name: /C12/ });
    const tabList = screen.getByRole("tablist", { name: "검증 케이스" });
    const tabs = within(tabList).getAllByRole("tab");
    expect(tabs).toHaveLength(12);
    expect(tabs[11]).toHaveTextContent("C12");
  });
});
