import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HotSwapTab } from "@/components/admin/backups/HotSwapTab";

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

const PLAN = {
  current_database: "kor_travel_geo",
  restore_database: "kor_travel_geo_restore",
  previous_alias: "kor_travel_geo_previous",
  maintenance_database: "postgres",
  typed_confirmation: "HOT_SWAP kor_travel_geo FROM kor_travel_geo_restore",
  rollback_confirmation: "ROLLBACK_HOT_SWAP kor_travel_geo FROM kor_travel_geo_previous",
  previous_alias_retention_days: 7,
  can_execute: true,
  blockers: [],
  steps: ["terminate", "rename current→previous", "rename restore→current"]
};

describe("HotSwapTab (T-250)", () => {
  beforeEach(() => {
    apiMocks.postJson.mockReset();
    apiMocks.requestJson.mockReset();
    // restore_database datalist용 복원 이력 조회 (db_restore_log)
    apiMocks.requestJson.mockResolvedValue([]);
  });

  it("gates execute behind plan + maintenance window + exact confirmation", async () => {
    apiMocks.postJson.mockImplementation(async (path: string) => {
      if (path.endsWith("/hot-swap-plan")) return PLAN;
      if (path.endsWith("/maintenance-windows")) {
        return { maintenance_window_id: "mw-1", kind: "restore", state: "active" };
      }
      return {};
    });

    render(<HotSwapTab />);
    fireEvent.change(screen.getByLabelText("복원된 DB 이름"), {
      target: { value: "kor_travel_geo_restore" }
    });
    fireEvent.click(screen.getByRole("button", { name: "plan 생성" }));

    // plan rendered with the can-execute badge
    await waitFor(() => expect(screen.getByText("kor_travel_geo_previous")).toBeTruthy());
    expect(screen.getByText("가능")).toBeTruthy();

    // execute is disabled with no window and no confirmation
    const execBtn = screen.getByRole("button", { name: /hot-swap 실행/ });
    expect((execBtn as HTMLButtonElement).disabled).toBe(true);

    // open the maintenance window
    fireEvent.click(screen.getByRole("button", { name: /maintenance window 열기/ }));
    await waitFor(() => expect(screen.getByText(/window mw-1/)).toBeTruthy());

    // still disabled until the exact typed confirmation is entered
    expect((execBtn as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("typed confirmation"), {
      target: { value: PLAN.typed_confirmation }
    });
    // TypedConfirmField가 실시간 일치 피드백을 보여 준다
    expect(screen.getAllByText("확인 문구가 일치합니다.").length).toBeGreaterThan(0);
    expect((execBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("T-312: disables plan on a shared DB instance but keeps source re-verify", async () => {
    render(
      <HotSwapTab
        lifecycle={{
          mode: "auto",
          supported: false,
          reason: "role kor_travel_geo_app: CREATEDB 권한 없음",
          checked_at: "2026-09-29T00:00:00Z"
        }}
      />
    );
    expect(
      screen.getByText(/Hot-swap: 공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행/)
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("복원된 DB 이름"), {
      target: { value: "kor_travel_geo_restore" }
    });
    const planButton = screen.getByRole("button", { name: "plan 생성" });
    expect((planButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(planButton);
    expect(apiMocks.postJson).not.toHaveBeenCalled();
    // source 재검증은 DB 수명주기 권한이 필요 없으므로 그대로 쓸 수 있다
    expect(
      (screen.getByRole("button", { name: "source 재검증" }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("T-312: a supported instance keeps plan enabled", async () => {
    render(
      <HotSwapTab
        lifecycle={{ mode: "auto", supported: true, checked_at: "2026-09-29T00:00:00Z" }}
      />
    );
    expect(screen.queryByText(/공용 DB instance에서는 지원하지 않음/)).toBeNull();
    fireEvent.change(screen.getByLabelText("복원된 DB 이름"), {
      target: { value: "kor_travel_geo_restore" }
    });
    expect(
      (screen.getByRole("button", { name: "plan 생성" }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("surfaces plan blockers and keeps the window button disabled", async () => {
    apiMocks.postJson.mockResolvedValue({
      ...PLAN,
      can_execute: false,
      blockers: ["restore database does not exist in cluster: kor_travel_geo_restore"]
    });

    render(<HotSwapTab />);
    fireEvent.change(screen.getByLabelText("복원된 DB 이름"), {
      target: { value: "kor_travel_geo_restore" }
    });
    fireEvent.click(screen.getByRole("button", { name: "plan 생성" }));

    await waitFor(() => expect(screen.getByText(/does not exist in cluster/)).toBeTruthy());
    expect(screen.getByText("불가")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /maintenance window 열기/ }) as HTMLButtonElement).disabled
    ).toBe(true);
  });
});
