import { describe, expect, it } from "vitest";

import { fileInventoryPaths, fileKindLabels, lifecycleOf } from "@/lib/file-inventory";

describe("fileInventoryPaths.list", () => {
  it("omits default kind and empty filters", () => {
    expect(fileInventoryPaths.list({})).toBe("/admin/storage/files");
    expect(fileInventoryPaths.list({ kind: "all" })).toBe("/admin/storage/files");
  });

  it("encodes kind, category, lifecycle and temporary filters", () => {
    expect(
      fileInventoryPaths.list({
        kind: "artifact",
        category: "db_backup",
        lifecycle: "available",
        temporaryOnly: true,
        limit: 50
      })
    ).toBe(
      "/admin/storage/files?kind=artifact&category=db_backup&lifecycle=available&temporary_only=true&limit=50"
    );
  });

  it("encodes the source group detail path", () => {
    expect(fileInventoryPaths.sourceGroupDetail("g 1")).toBe(
      "/admin/storage/files/source-groups/g%201"
    );
  });
});

describe("lifecycleOf", () => {
  it("maps known lifecycle buckets to Korean labels + tones", () => {
    expect(lifecycleOf("serving").label).toBe("서빙 사용 중");
    expect(lifecycleOf("serving").tone).toBe("ok");
    expect(lifecycleOf("orphan").tone).toBe("warn");
    expect(lifecycleOf("missing").tone).toBe("error");
  });

  it("falls back to the raw value for unknown buckets", () => {
    expect(lifecycleOf("mystery").label).toBe("mystery");
    expect(lifecycleOf("mystery").tone).toBe("neutral");
  });
});

describe("fileKindLabels", () => {
  it("labels every inventory kind in Korean", () => {
    expect(fileKindLabels.source_group).toBe("원천 파일");
    expect(fileKindLabels.artifact).toBe("백업/산출물");
    expect(fileKindLabels.orphan_object).toBe("저장소 객체");
  });
});
