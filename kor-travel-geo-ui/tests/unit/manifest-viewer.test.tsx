import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ManifestViewer } from "@/components/admin/backups/ManifestViewer";
import { inventoryTone } from "@/components/admin/backups/manifest-utils";
import type { BackupArtifact } from "@/lib/api";

const ARTIFACT: BackupArtifact = {
  artifact_id: "art-1",
  artifact_type: "db_backup",
  state: "available",
  storage_kind: "local_file",
  display_name: "backup-202606.tar.zst",
  size_bytes: 2048,
  retention_class: "scheduled",
  expires_at: "2026-07-16T00:00:00Z",
  created_at: "2026-06-16T00:00:00Z",
  source_set_yyyymm: { juso: "202603", locsum: "202604" },
  source_set_mixed: true,
  source_inventory_ok: false,
  manifest: {
    source_inventory_verification: { ok: false, missing: 2 },
    active_serving: {
      serving_release_id: "rel-9",
      dataset_snapshot_id: "snap-9",
      source_match_set_id: "ms-9"
    }
  }
};

describe("inventoryTone (T-252)", () => {
  it("maps ok/false/null to tone+label", () => {
    expect(inventoryTone(true)).toEqual({ tone: "ok", label: "검증됨" });
    expect(inventoryTone(false)).toEqual({ tone: "error", label: "불일치" });
    expect(inventoryTone(null)).toEqual({ tone: "warn", label: "미검증" });
    expect(inventoryTone(undefined)).toEqual({ tone: "warn", label: "미검증" });
  });
});

describe("ManifestViewer (T-252)", () => {
  it("surfaces reproducibility context and closes", () => {
    const onClose = vi.fn();
    render(<ManifestViewer artifact={ARTIFACT} onClose={onClose} />);

    const dialog = screen.getByRole("dialog", { name: "백업 manifest 재현성 뷰어" });
    // retention + verification verdict
    expect(within(dialog).getByText("scheduled")).toBeTruthy();
    expect(within(dialog).getByText("불일치")).toBeTruthy();
    // source_set 기준월 per kind (value appears in the section and the raw manifest block)
    expect(within(dialog).getByText("juso")).toBeTruthy();
    expect(within(dialog).getAllByText(/202603/).length).toBeGreaterThan(0);
    // active serving lineage
    expect(within(dialog).getByText(/release · rel-9/)).toBeTruthy();
    expect(within(dialog).getByText(/match set · ms-9/)).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
