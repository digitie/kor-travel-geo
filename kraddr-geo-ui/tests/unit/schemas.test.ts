import { describe, expect, it } from "vitest";
import { explainFormSchema, geocodeFormSchema, reverseFormSchema } from "@/lib/schemas";

describe("form schemas", () => {
  it("EXPLAIN은 SELECT/WITH만 통과시킨다", () => {
    expect(explainFormSchema.parse({ sql: "SELECT 1" }).sql).toBe("SELECT 1");
    expect(() => explainFormSchema.parse({ sql: "DELETE FROM x" })).toThrow();
    expect(() => explainFormSchema.parse({ sql: "SELECT 1;" })).toThrow();
  });

  it("역지오코딩 좌표는 한국 lon/lat 범위를 벗어나면 실패한다", () => {
    expect(reverseFormSchema.parse({ x: "127.1", y: "37.4" }).radius_m).toBe(200);
    expect(() => reverseFormSchema.parse({ x: "20", y: "37.4" })).toThrow();
  });

  it("지오코딩 디버그 입력은 v2 fallback 값을 사용한다", () => {
    expect(geocodeFormSchema.parse({ address: "테헤란로 152" }).fallback).toBe("none");
    expect(geocodeFormSchema.parse({ address: "테헤란로 152", fallback: "api" }).fallback).toBe(
      "api"
    );
    expect(() =>
      geocodeFormSchema.parse({ address: "테헤란로 152", fallback: "local_only" })
    ).toThrow();
  });
});
