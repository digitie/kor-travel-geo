import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RestoreReconcilePanel } from "@/components/admin/backups/RestoreReconcilePanel";
import { reconcileFromManifest } from "@/components/admin/backups/restore-reconcile-utils";

const apiMocks = vi.hoisted(() => ({ requestJson: vi.fn(), postJson: vi.fn() }));

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  backendPath: (p: string) => (p.startsWith("/v1") || p.startsWith("/v2") ? p : `/v1${p}`),
  requestJson: apiMocks.requestJson,
  postJson: apiMocks.postJson
}));

describe("reconcileFromManifest (T-253)", () => {
  it("extracts row_count_verification, null for legacy", () => {
    expect(reconcileFromManifest(undefined)).toBeNull();
    expect(reconcileFromManifest({ target_database: "x" })).toBeNull();
    const rec = reconcileFromManifest({ row_count_verification: { ok: true } });
    expect(rec?.ok).toBe(true);
  });
});

const RESTORE_LOG = {
  artifact_id: "rl-1",
  artifact_type: "db_restore_log",
  state: "available",
  storage_kind: "none",
  display_name: "restore_kor_travel_geo_restore",
  created_at: "2026-06-16T01:02:03Z",
  manifest: {
    target_database: "kor_travel_geo_restore",
    row_count_verification: {
      ok: false,
      target_database: "kor_travel_geo_restore",
      row_count_diffs: [
        { object: "tl_juso_text", expected: 100, actual: 100, match: true },
        { object: "mv_geocode_target", expected: 100, actual: 90, match: false }
      ],
      mv_geocode_target_rows: 90,
      mv_nonempty_ok: true,
      sppn_rows: 24204,
      warnings: ["row_count mismatch: mv_geocode_target"]
    }
  }
};

describe("RestoreReconcilePanel (T-253)", () => {
  beforeEach(() => {
    apiMocks.requestJson.mockReset();
  });

  it("renders FAIL with the mismatched object and warning", async () => {
    apiMocks.requestJson.mockResolvedValue([RESTORE_LOG]);
    render(<RestoreReconcilePanel />);

    await waitFor(() => expect(screen.getByText("FAIL")).toBeTruthy());
    expect(screen.getAllByText(/kor_travel_geo_restore/).length).toBeGreaterThan(0);
    // the mismatched row shows a mismatch badge
    const table = screen.getByRole("table");
    expect(within(table).getByText("mv_geocode_target")).toBeTruthy();
    expect(within(table).getByText("mismatch")).toBeTruthy();
    expect(screen.getByText(/row_count mismatch: mv_geocode_target/)).toBeTruthy();
  });

  it("shows an empty hint when there are no restore logs", async () => {
    apiMocks.requestJson.mockResolvedValue([]);
    render(<RestoreReconcilePanel />);
    await waitFor(() => expect(screen.getByText(/복원 기록이 없습니다/)).toBeTruthy());
  });
});
