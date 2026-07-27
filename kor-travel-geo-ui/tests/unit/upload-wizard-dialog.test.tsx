import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UploadWizardDialog } from "@/components/admin/source-files/UploadWizardDialog";
import type { SourceFileCategoryInfo } from "@/lib/source-files";

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn(),
  ApiError: class ApiErrorMock extends Error {
    status: number;
    body: unknown;
    detail: unknown;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
      this.body = null;
      this.detail = null;
    }
  }
}));

const multipartMocks = vi.hoisted(() => ({
  uploadSlotFile: vi.fn()
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  ApiError: apiMocks.ApiError,
  backendPath: (path: string) =>
    path.startsWith("/v1") || path.startsWith("/v2") ? path : `/v1${path}`,
  getErrorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
  postJson: apiMocks.postJson,
  requestJson: vi.fn()
}));

vi.mock("@/lib/multipart-upload", () => ({
  uploadSlotFile: multipartMocks.uploadSlotFile
}));

const CATEGORY: SourceFileCategoryInfo = {
  category: "roadname_hangul_full",
  label: "도로명주소 한글 전체분",
  group_kind: "single_file",
  optional: false,
  role: "build_required",
  serving_usage: "serving_core",
  expected_member_kinds: ["rnaddrkor_txt"]
} as unknown as SourceFileCategoryInfo;

const SESSION = {
  upload_session_id: "sess-1",
  source_file_group_id: "group-1",
  category: "roadname_hangul_full",
  group_kind: "single_file",
  user_yyyymm: "202605",
  display_name: "rnaddrkor.zip",
  state: "awaiting_registration",
  storage_kind: "rustfs",
  expected_file_count: 1,
  uploaded_file_count: 0,
  max_bytes: 2_000_000_000,
  part_size_bytes: 64 * 1024 * 1024,
  file_slots: [{ slot: "archive", part_key: "archive", uploaded: false, received_bytes: 0 }],
  created_at: "2026-06-14T00:00:00Z",
  updated_at: "2026-06-14T00:00:00Z"
};

function renderDialog(
  onCompleted = vi.fn(),
  maxBytesByCategory: Map<string, number> = new Map()
) {
  const queryClient = new QueryClient();
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <UploadWizardDialog
        categories={[CATEGORY]}
        maxBytesByCategory={maxBytesByCategory}
        onCompleted={onCompleted}
        onOpenChange={onOpenChange}
        open
      />
    </QueryClientProvider>
  );
  return { onCompleted, onOpenChange };
}

describe("UploadWizardDialog (#201)", () => {
  beforeEach(() => {
    apiMocks.postJson.mockReset();
    multipartMocks.uploadSlotFile.mockReset();
  });

  it("walks category -> yyyymm -> drop file -> preview -> register", async () => {
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path.includes("/preview-validate")) {
        return {
          upload_session_id: "sess-1",
          category: "roadname_hangul_full",
          outcome: "passed",
          parts: [{ part_key: "archive", outcome: "passed", reasons: [], warnings: [] }],
          validator_version: "t127.2"
        };
      }
      if (path.includes("/register")) {
        return { ...SESSION, state: "available", registration_state: "registered" };
      }
      return SESSION; // create session
    });
    multipartMocks.uploadSlotFile.mockResolvedValue({ ...SESSION, state: "awaiting_registration" });

    const { onCompleted } = renderDialog();

    // step 1: pick category
    fireEvent.click(screen.getByRole("option", { name: /도로명주소 한글 전체분/ }));

    // step 2: yyyymm
    await waitFor(() => expect(screen.getByLabelText("기준년월")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("기준년월"), { target: { value: "202605" } });
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    // step 3: drop a file
    const file = new File(["x"], "rnaddrkor.zip", { type: "application/zip" });
    const input = screen.getByLabelText("업로드할 파일 선택");
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(screen.getAllByText("통과").length).toBeGreaterThan(0));
    expect(multipartMocks.uploadSlotFile).toHaveBeenCalledWith(
      expect.objectContaining({ sessionId: "sess-1", slotId: "archive" })
    );
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    // step 4: confirm + register
    await waitFor(() => expect(screen.getByRole("button", { name: "등록" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "등록" }));

    // #201 review fix: the success screen must render and stay open (not vanish because
    // the parent's onCompleted synchronously flips `open` to false) — onCompleted only
    // fires once the user explicitly dismisses the success screen.
    await waitFor(() => expect(screen.getByText(/업로드가 등록됐습니다/)).toBeTruthy());
    expect(onCompleted).not.toHaveBeenCalled();

    const doneScreen = screen.getByText(/업로드가 등록됐습니다/).closest(".wizard-done") as HTMLElement;
    fireEvent.click(within(doneScreen).getByRole("button", { name: "닫기" }));
    expect(onCompleted).toHaveBeenCalled();
  });

  it("#201 review fix: blocks an oversized file before creating a session", async () => {
    apiMocks.postJson.mockResolvedValue(SESSION);

    renderDialog(vi.fn(), new Map([["roadname_hangul_full", 10]]));

    fireEvent.click(screen.getByRole("option", { name: /도로명주소 한글 전체분/ }));
    await waitFor(() => expect(screen.getByLabelText("기준년월")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    const oversizedFile = new File(["x".repeat(100)], "rnaddrkor.zip", {
      type: "application/zip"
    });
    fireEvent.change(screen.getByLabelText("업로드할 파일 선택"), {
      target: { files: [oversizedFile] }
    });

    await waitFor(() => expect(screen.getAllByText(/크기 한도.*초과합니다/).length).toBeGreaterThan(0));
    expect(apiMocks.postJson).not.toHaveBeenCalled();
    expect(multipartMocks.uploadSlotFile).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
  });

  it("#201 review fix: retries preview-validate without recreating the session after a transient failure", async () => {
    let previewCalls = 0;
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path.includes("/preview-validate")) {
        previewCalls += 1;
        if (previewCalls === 1) {
          throw new apiMocks.ApiError("preview backend blip", 500);
        }
        return {
          upload_session_id: "sess-1",
          category: "roadname_hangul_full",
          outcome: "passed",
          parts: [{ part_key: "archive", outcome: "passed", reasons: [], warnings: [] }],
          validator_version: "t127.2"
        };
      }
      return SESSION; // create session
    });
    multipartMocks.uploadSlotFile.mockResolvedValue({ ...SESSION, state: "awaiting_registration" });

    renderDialog();

    fireEvent.click(screen.getByRole("option", { name: /도로명주소 한글 전체분/ }));
    await waitFor(() => expect(screen.getByLabelText("기준년월")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    const file = new File(["x"], "rnaddrkor.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("업로드할 파일 선택"), { target: { files: [file] } });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "사전 점검 다시 시도" })).toBeTruthy()
    );
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "사전 점검 다시 시도" }));

    await waitFor(() => expect(screen.getAllByText("통과").length).toBeGreaterThan(0));
    // Only one session should ever have been created — the retry re-used it.
    const createSessionCalls = apiMocks.postJson.mock.calls.filter(
      (call: unknown[]) => call[0] === "/admin/source-files/upload-sessions"
    );
    expect(createSessionCalls).toHaveLength(1);
    expect(multipartMocks.uploadSlotFile).toHaveBeenCalledTimes(1);
  });

  it("shows a clear message on a 409 duplicate-session conflict", async () => {
    apiMocks.postJson.mockRejectedValue(new apiMocks.ApiError("conflict", 409));

    renderDialog();

    fireEvent.click(screen.getByRole("option", { name: /도로명주소 한글 전체분/ }));
    await waitFor(() => expect(screen.getByLabelText("기준년월")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("기준년월"), { target: { value: "202605" } });
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    const file = new File(["x"], "rnaddrkor.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText("업로드할 파일 선택"), { target: { files: [file] } });

    await waitFor(() =>
      expect(screen.getByText(/이미 같은 카테고리·기준월의 업로드 세션이 진행 중입니다/)).toBeTruthy()
    );
    expect(multipartMocks.uploadSlotFile).not.toHaveBeenCalled();
  });
});
