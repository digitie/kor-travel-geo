import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RestoreWizard } from "@/components/admin/backups/RestoreWizard";

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn(),
  requestJson: vi.fn()
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  backendPath: (path: string) =>
    path.startsWith("/v1") || path.startsWith("/v2") ? path : `/v1${path}`,
  getErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : String(error),
  postJson: apiMocks.postJson,
  requestJson: apiMocks.requestJson
}));

const ARTIFACT = {
  artifact_id: "art-1",
  artifact_type: "db_backup",
  state: "available",
  display_name: "backup-202606.tar.zst",
  size_bytes: 2048,
  created_at: "2026-06-16T00:00:00Z",
  manifest: {
    backup: { profile: "serving-ready" },
    database: { postgres_version: "16.4", postgis_version: "3.5.2" },
    row_counts: { mv_geocode_target: 100 }
  }
};

describe("RestoreWizard (T-249)", () => {
  beforeEach(() => {
    apiMocks.requestJson.mockReset();
    apiMocks.postJson.mockReset();
    apiMocks.requestJson.mockResolvedValue([ARTIFACT]);
  });

  async function gotoStep2() {
    render(<RestoreWizard />);
    await waitFor(() => expect(screen.getByRole("option", { name: /backup-202606/ })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("복원할 백업본"), {
      target: { value: "art-1" }
    });
    fireEvent.click(screen.getByRole("button", { name: /다음/ }));
  }

  it("walks new_database through preview -> dry-run -> submit", async () => {
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path.endsWith("/dry-run")) {
        return {
          can_restore: true,
          mode: "new_database",
          target_database: "kor_travel_geo_restore",
          archive_sha256_ok: true,
          internal_checksums_ok: true,
          manifest_ok: true,
          blockers: [],
          warnings: []
        };
      }
      return { job_id: "job-1", kind: "db_restore", state: "queued", progress: 0 };
    });

    await gotoStep2();
    // step 2: manifest preview shows the backup PostgreSQL version
    expect(screen.getByText("16.4")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /dry-run 실행/ }));

    // step 3: dry-run verdict
    await waitFor(() => expect(screen.getByText("복원 가능")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /확인 단계로/ }));

    // step 4: new_database needs no confirmation → submit enabled
    const submit = screen.getByRole("button", { name: /복원 시작/ });
    expect((submit as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(submit);
    await waitFor(() => expect(screen.getByText(/복원 job이 제출됐습니다/)).toBeTruthy());
  });

  it("blocks submit when the dry-run says can_restore=false (Codex H1)", async () => {
    apiMocks.postJson.mockResolvedValue({
      can_restore: false,
      mode: "new_database",
      target_database: "kor_travel_geo_restore",
      blockers: ["restore target database is not empty"],
      warnings: []
    });

    await gotoStep2();
    fireEvent.click(screen.getByRole("button", { name: /dry-run 실행/ }));
    await waitFor(() => expect(screen.getByText("복원 불가")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /확인 단계로/ }));

    // step 4: blocker warning shown AND submit disabled even for new_database
    expect(screen.getByText(/복원 불가로 판정/)).toBeTruthy();
    const submit = screen.getByRole("button", { name: /복원 시작/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });

  it("validates target_database as a PostgreSQL identifier before step 2", async () => {
    render(<RestoreWizard />);
    await waitFor(() => expect(screen.getByRole("option", { name: /backup-202606/ })).toBeTruthy());
    // artifact 옵션 텍스트에 생성일이 포함된다
    expect(screen.getByRole("option", { name: /2026-06-16/ })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("복원할 백업본"), {
      target: { value: "art-1" }
    });

    const next = screen.getByRole("button", { name: /다음/ });
    fireEvent.change(screen.getByLabelText("복원 대상 DB 이름"), {
      target: { value: "Bad Name!" }
    });
    expect(screen.getByText(/소문자\/숫자\/밑줄만 사용/)).toBeTruthy();
    expect((next as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("복원 대상 DB 이름"), {
      target: { value: "kor_travel_geo_restore" }
    });
    expect((next as HTMLButtonElement).disabled).toBe(false);
  });

  it("gates replace_current submit on the exact typed confirmation", async () => {
    apiMocks.postJson.mockResolvedValue({
      can_restore: true,
      mode: "replace_current",
      target_database: "kor_travel_geo",
      blockers: [],
      warnings: []
    });

    render(<RestoreWizard />);
    await waitFor(() => expect(screen.getByRole("option", { name: /backup-202606/ })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("복원할 백업본"), {
      target: { value: "art-1" }
    });
    // 복원 모드는 라디오 카드 2개 — 위험(replace_current) 카드를 선택한다
    fireEvent.click(screen.getByRole("radio", { name: /운영 DB 교체/ }));
    fireEvent.change(screen.getByLabelText("복원 대상 DB 이름"), {
      target: { value: "kor_travel_geo" }
    });
    fireEvent.click(screen.getByRole("button", { name: /다음/ }));
    fireEvent.click(screen.getByRole("button", { name: /dry-run 실행/ }));
    await waitFor(() => expect(screen.getByText("복원 가능")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /확인 단계로/ }));

    // submit disabled until the exact confirmation is typed
    const submit = screen.getByRole("button", { name: /복원 시작/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("typed confirmation"), {
      target: { value: "RESTORE kor_travel_geo" }
    });
    expect(screen.getByText("확인 문구가 일치합니다.")).toBeTruthy();
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });
});
