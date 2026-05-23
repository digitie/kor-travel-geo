import { describe, expect, it } from "vitest";
import { backendPath } from "@/lib/api";

describe("backendPath", () => {
  it("백엔드 v1 prefix를 안정적으로 붙인다", () => {
    expect(backendPath("/address/geocode")).toBe("/v1/address/geocode");
    expect(backendPath("admin/tables")).toBe("/v1/admin/tables");
    expect(backendPath("/v1/admin/loads")).toBe("/v1/admin/loads");
  });
});
