import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourceFilesPanel } from "@/components/admin/source-files/SourceFilesPanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn(),
  requestJson: vi.fn()
}));

// ApiError/getErrorMessage는 실제 구현을 유지해 detail 파싱 계약까지 함께 검증한다.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    postJson: apiMocks.postJson,
    requestJson: apiMocks.requestJson
  };
});

const CATEGORY_CATALOG = {
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
    },
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
  // 앱 셸(app/providers.tsx)과 동일하게 TooltipProvider로 감싼다 (셀 툴팁 의존).
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <SourceFilesPanel initialTab={initialTab} />
      </TooltipProvider>
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
    // T-224: 활성 매칭 세트 기준 '현재 서빙 포함/미포함'을 카드에 표시한다.
    await screen.findByText("현재 서빙 포함");
    const roadServingCard = screen
      .getByText("도로명주소 한글 전체분")
      .closest(".source-card") as HTMLElement;
    expect(within(roadServingCard).getByText("현재 서빙 포함")).toBeInTheDocument();
    const epostServingCard = screen
      .getByText("epost 사서함")
      .closest(".source-card") as HTMLElement;
    expect(within(epostServingCard).getByText("현재 서빙 미포함")).toBeInTheDocument();
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path === "/admin/source-files/epost-fetch")
        return {
          category: "epost_pobox_full",
          upload_session: {
            ...RESUMABLE_SESSION,
            upload_session_id: "source_upload_epost",
            category: "epost_pobox_full",
            state: "registered",
            registered_at: "2026-06-15T00:00:00Z"
          },
          registration: {
            source_file_group_id: "group_epost",
            category: "epost_pobox_full",
            group_kind: "single_file",
            state: "available",
            validation_state: "passed",
            user_yyyymm: "202606"
          },
          load_job_id: "job_epost",
          load_job_kind: "pobox_load",
          validation: { row_count: 1 },
          warnings: []
        };
      return { ok: true };
    });
    const epostCard = screen.getByText("epost 사서함").closest(".source-card") as HTMLElement;
    const epostInput = within(epostCard).getByPlaceholderText("예: 202606");
    fireEvent.change(epostInput, { target: { value: "202606" } });
    const epostButton = within(epostCard).getByRole("button", { name: "epost 받기" });
    expect(epostButton).not.toBeDisabled();
    fireEvent.click(epostButton);
    await waitFor(() =>
      expect(apiMocks.postJson).toHaveBeenCalledWith(
        "/admin/source-files/epost-fetch",
        expect.objectContaining({
          category: "epost_pobox_full",
          user_yyyymm: "202606",
          enqueue_load: true
        })
      )
    );
    expect(await screen.findByText(/job_epost/)).toBeInTheDocument();
    // 재개 가능한 업로드 목록
    expect(await screen.findByText("재개 가능한 업로드")).toBeInTheDocument();
  });

  it("epost 서버 fetch 실패 시 카드에 인라인 에러를 표시한다", async () => {
    renderPanel("upload");
    const epostCard = (await screen.findByText("epost 사서함")).closest(
      ".source-card"
    ) as HTMLElement;
    apiMocks.postJson.mockImplementationOnce(async () => {
      throw new ApiError(502, JSON.stringify({ detail: "epost 서버 응답 없음" }));
    });
    fireEvent.change(within(epostCard).getByPlaceholderText("예: 202606"), {
      target: { value: "202606" }
    });
    fireEvent.click(within(epostCard).getByRole("button", { name: "epost 받기" }));
    expect(
      await within(epostCard).findByText(/epost 서버 fetch 실패: epost 서버 응답 없음/)
    ).toBeInTheDocument();
  });

  it("업로드 409 응답 시 중복 세션 다이얼로그를 띄운다", async () => {
    renderPanel("upload");
    await screen.findByText("도로명주소 한글 전체분");

    apiMocks.postJson.mockImplementationOnce(async () => {
      throw new ApiError(
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
    // 30일 증가량 (512 B) + 미등록(1024 B = 1.0 KB) + 미해결 이슈(open 2건, error 1건)
    expect(await within(summary).findByText("최근 30일 증가")).toBeInTheDocument();
    expect(within(summary).getByText("512 B")).toBeInTheDocument();
    expect(within(summary).getByText("1.0 KB")).toBeInTheDocument();
    const openDt = within(summary).getByText("미해결 이슈");
    const openDd = openDt.parentElement?.querySelector("dd");
    await waitFor(() => expect(openDd).toHaveTextContent("2"));
    const errorDt = within(summary).getByText("오류(error) 이슈");
    expect(errorDt.parentElement?.querySelector("dd")).toHaveTextContent("1");
  });

  it("RustFS 정합성 탭에 실행/이슈/용량을 표시한다", async () => {
    renderPanel("reconcile");
    await screen.findByText("정합성 실행");
    // 12 issue_type 라벨 중 hash_mismatch 매핑이 나타난다
    expect(await screen.findByText("해시 불일치")).toBeInTheDocument();
    // capacity panel
    expect(await screen.findByRole("heading", { name: "용량" })).toBeInTheDocument();
  });

  it("정리 대상을 선택해 typed-confirmation 일괄 영구 삭제(T-212)를 호출한다", async () => {
    renderPanel("reconcile");
    await screen.findByText("정합성 실행");

    // 정리 대상(object_missing_db) 행의 선택 체크박스
    const rowCheckbox = await screen.findByLabelText(/정리 대상 선택:/);
    fireEvent.click(rowCheckbox);

    // 일괄 삭제 버튼 → 다이얼로그
    fireEvent.click(screen.getByRole("button", { name: /선택 항목 영구 삭제/ }));
    const dialog = await screen.findByRole("alertdialog", { name: "원천 객체 영구 삭제" });
    const execButton = within(dialog).getByRole("button", { name: /영구 삭제 실행/ });

    // 확인 문구 입력 전에는 비활성
    expect(execButton).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("hard-delete 확인 문구"), {
      target: { value: "HARD-DELETE-SOURCES" }
    });
    // manifest_ack를 확인하기 전에는 여전히 비활성 (UI 필수 게이트)
    expect(execButton).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /manifest 없이 진행/ }));
    expect(execButton).not.toBeDisabled();

    fireEvent.click(execButton);
    await waitFor(() =>
      expect(apiMocks.postJson).toHaveBeenCalledWith(
        "/admin/source-files/bulk-hard-delete",
        expect.objectContaining({
          object_keys: ["source/electronic_map_full/orphan-36.zip"],
          typed_confirmation: "HARD-DELETE-SOURCES",
          manifest_ack: true
        })
      )
    );
  });

  it("capacity가 한도 초과면 retention 경고(T-212 UI 경고)를 노출한다", async () => {
    apiMocks.requestJson.mockImplementation(async (path: string) => {
      if (path.startsWith("/admin/source-files/reconcile/") && path.includes("/items"))
        return RECONCILE_ITEMS;
      if (path.startsWith("/admin/source-files/reconcile")) return RECONCILE_RUNS;
      if (path === "/admin/source-files/capacity")
        return {
          ...CAPACITY,
          over_threshold: true,
          retention: {
            over_threshold: true,
            reclaimable_bytes: 4096,
            eligible_object_count: 3,
            guidance: "정리 대상 객체를 일괄 hard-delete 하세요"
          }
        };
      return [];
    });
    renderPanel("reconcile");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("저장소 용량 한도 초과");
    expect(screen.getByText("정리 대상 객체를 일괄 hard-delete 하세요")).toBeInTheDocument();
    expect(within(alert).getByText("4.0 KB")).toBeInTheDocument();
  });

  it("일괄 삭제 결과를 구조화 요약으로 표시한다", async () => {
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path === "/admin/source-files/bulk-hard-delete")
        return {
          requested_count: 1,
          hard_deleted_count: 1,
          delete_failed_count: 0,
          skipped_count: 0,
          results: [
            {
              object_key: "source/electronic_map_full/orphan-36.zip",
              outcome: "hard_deleted"
            }
          ],
          affected_match_set_ids: []
        };
      return { ok: true };
    });
    renderPanel("reconcile");
    await screen.findByText("정합성 실행");
    fireEvent.click(await screen.findByLabelText(/정리 대상 선택:/));
    fireEvent.click(screen.getByRole("button", { name: /선택 항목 영구 삭제/ }));
    const dialog = await screen.findByRole("alertdialog", { name: "원천 객체 영구 삭제" });
    fireEvent.change(within(dialog).getByLabelText("hard-delete 확인 문구"), {
      target: { value: "HARD-DELETE-SOURCES" }
    });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /manifest 없이 진행/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: /영구 삭제 실행/ }));
    // '최근 결과' 패널은 상시 렌더되므로, 응답 요약(dt '영구 삭제')이 나타날 때까지 기다린다.
    const deletedDt = await screen.findByText("영구 삭제");
    const summary = deletedDt.closest(".panel") as HTMLElement;
    expect(deletedDt.parentElement?.querySelector("dd")).toHaveTextContent("1");
    // raw JSON dump 대신 구조화 요약을 쓴다
    expect(within(summary).queryByText(/requested_count/)).not.toBeInTheDocument();
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
