import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DatasetVersionDetailDialog } from "@/components/admin/ops/DatasetVersionDetailDialog";
import type { ServingRelease } from "@/lib/api";

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn()
}));

vi.mock("@/lib/api", () => ({
  getErrorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
  postJson: apiMocks.postJson
}));

const ACTIVE_RELEASE: ServingRelease = {
  serving_release_id: "rel-1",
  dataset_snapshot_id: "snap-1",
  state: "active",
  release_kind: "full_load",
  mv_name: "mv_geocode_target",
  created_at: "2026-06-16T00:00:00Z",
  version_token: "dv1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  change_type: "full",
  reference_months: { juso: "202606", locsum: "202605" },
  reference_months_mixed: true,
  source_set: { juso: "202606" }
};

const LEGACY_RELEASE: ServingRelease = {
  serving_release_id: "rel-0",
  dataset_snapshot_id: "snap-0",
  state: "superseded",
  release_kind: "full_load",
  mv_name: "mv_geocode_target",
  created_at: "2026-01-01T00:00:00Z"
};

describe("DatasetVersionDetailDialog (T-291d)", () => {
  beforeEach(() => {
    apiMocks.postJson.mockReset();
  });

  it("shows the release's own fields and closes", () => {
    const onClose = vi.fn();
    render(<DatasetVersionDetailDialog release={ACTIVE_RELEASE} onClose={onClose} />);

    const dialog = screen.getByRole("dialog", { name: "데이터셋 버전 상세" });
    expect(within(dialog).getByText("full")).toBeTruthy();
    expect(within(dialog).getByText("juso")).toBeTruthy();
    expect(within(dialog).getByText("혼합")).toBeTruthy();
    // curl 스니펫은 이 release 자신의 version_token을 known_version으로 담는다.
    expect(
      within(dialog).getByText((_, el) => el?.tagName === "PRE" && (el.textContent ?? "").includes(ACTIVE_RELEASE.version_token!))
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("sends this release's version_token as known_version and reports it's still current", async () => {
    apiMocks.postJson.mockResolvedValue({
      status: "OK",
      query_id: "q1",
      available: true,
      changed: false,
      known_version_found: true,
      current: { version_token: ACTIVE_RELEASE.version_token, activated_at: ACTIVE_RELEASE.created_at, change_type: "full" }
    });
    render(<DatasetVersionDetailDialog release={ACTIVE_RELEASE} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "POST /v2/dataset/version 호출" }));

    await waitFor(() => expect(apiMocks.postJson).toHaveBeenCalledTimes(1));
    expect(apiMocks.postJson).toHaveBeenCalledWith("/v2/dataset/version", {
      known_version: ACTIVE_RELEASE.version_token
    });
    await screen.findByText(/이 release가 지금도 현재 활성 릴리스입니다/);
  });

  // 회귀 방지: 예전엔 known_version 없이 항상 호출해 preview가 이 행이 아니라 "현재 활성
  // 릴리스"를 보여줬다 — superseded 행에서 changed:true를 받으면 그 사실을 명시해야 한다.
  it("warns when the previewed current release differs from this (superseded) row", async () => {
    apiMocks.postJson.mockResolvedValue({
      status: "OK",
      query_id: "q2",
      available: true,
      changed: true,
      known_version_found: true,
      current: { version_token: "dv1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", activated_at: "2026-07-01T00:00:00Z", change_type: "delta" }
    });
    render(<DatasetVersionDetailDialog release={ACTIVE_RELEASE} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "POST /v2/dataset/version 호출" }));

    await waitFor(() => expect(apiMocks.postJson).toHaveBeenCalledTimes(1));
    await screen.findByText(/더 이상 현재 활성 릴리스가 아닙니다/);
    expect(screen.getAllByText(/dv1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/).length).toBeGreaterThan(0);
  });

  it("calls without known_version for a legacy release with no version_token", async () => {
    apiMocks.postJson.mockResolvedValue({ status: "OK", query_id: "q3", available: true });
    render(<DatasetVersionDetailDialog release={LEGACY_RELEASE} onClose={vi.fn()} />);

    expect(screen.getByText(/이 release는 version_token이 없어/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "POST /v2/dataset/version 호출" }));

    await waitFor(() => expect(apiMocks.postJson).toHaveBeenCalledTimes(1));
    expect(apiMocks.postJson).toHaveBeenCalledWith("/v2/dataset/version", {});
  });

  it("surfaces a preview error message", async () => {
    apiMocks.postJson.mockRejectedValue(new Error("network unreachable"));
    render(<DatasetVersionDetailDialog release={ACTIVE_RELEASE} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "POST /v2/dataset/version 호출" }));

    await screen.findByText("network unreachable");
  });
});
