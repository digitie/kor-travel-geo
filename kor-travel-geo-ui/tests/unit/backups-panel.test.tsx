import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BackupsPanel } from "@/components/admin/BackupsPanel";

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn(),
  requestJson: vi.fn()
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  backendPath: (path: string) =>
    path.startsWith("/v1") || path.startsWith("/v2") ? path : `/v1${path}`,
  postJson: apiMocks.postJson,
  requestJson: apiMocks.requestJson
}));

const ARTIFACT = {
  artifact_id: "art-1",
  artifact_type: "db_backup",
  state: "available",
  display_name: "backup-202606.tar.zst",
  size_bytes: 1024,
  sha256: "abc123",
  manifest: { backup: { profile: "serving-ready" } }
};

function mockApiByPath() {
  apiMocks.requestJson.mockImplementation(async (path: string) => {
    if (path.startsWith("/admin/backups/allowed-dirs")) {
      return { dirs: [], default_dir: null };
    }
    if (path.startsWith("/admin/backups")) {
      return [ARTIFACT];
    }
    if (path.startsWith("/admin/jobs")) {
      return [];
    }
    return [];
  });
}

describe("BackupsPanel tab shell (T-248)", () => {
  beforeEach(() => {
    apiMocks.requestJson.mockReset();
    apiMocks.postJson.mockReset();
    mockApiByPath();
  });

  it("renders the five workflow tabs and the overview next-action guide", async () => {
    render(<BackupsPanel />);
    const tablist = await screen.findByRole("tablist", { name: "백업/복원 관리 탭" });
    expect(tablist).toBeTruthy();
    for (const label of ["개요", "백업", "복원", "Hot-swap", "작업"]) {
      expect(screen.getByRole("tab", { name: label })).toBeTruthy();
    }
    // overview is the default tab → the workflow guide is shown
    expect(screen.getByText("백업/복원 다음 액션")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText(/사용 가능한 백업 1개/)).toBeTruthy()
    );
  });

  it("switches to the backup tab and shows the create form + artifacts", async () => {
    render(<BackupsPanel />);
    await screen.findByRole("tablist", { name: "백업/복원 관리 탭" });
    fireEvent.click(screen.getByRole("tab", { name: "백업" }));
    expect(screen.getByText("DB Backup")).toBeTruthy();
    expect(screen.getByText("Backup Artifacts")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText("backup-202606.tar.zst")).toBeTruthy()
    );
  });

  it("shows the hot-swap guide pointing at the T-250 wizard", async () => {
    render(<BackupsPanel />);
    await screen.findByRole("tablist", { name: "백업/복원 관리 탭" });
    fireEvent.click(screen.getByRole("tab", { name: "Hot-swap" }));
    expect(screen.getByText(/운영 DB 교체/)).toBeTruthy();
    expect(screen.getByText(/T-250/)).toBeTruthy();
  });
});
