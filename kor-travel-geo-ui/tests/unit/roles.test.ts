import { describe, expect, it } from "vitest";
import { roleLabel, roleLabels } from "@/lib/roles";

describe("role labels (T-226)", () => {
  it("labels known roles with the Korean description", () => {
    expect(roleLabel("destructive_admin")).toBe("destructive_admin (파괴적 작업 관리)");
    expect(roleLabel("rebuild_operator")).toBe("rebuild_operator (DB 재구성 운영)");
  });

  it("falls back to the raw role for unknown roles", () => {
    expect(roleLabel("system")).toBe("system");
  });

  it("joins multiple roles with +", () => {
    expect(roleLabels(["rebuild_operator", "destructive_admin"])).toBe(
      "rebuild_operator (DB 재구성 운영) + destructive_admin (파괴적 작업 관리)"
    );
  });
});
