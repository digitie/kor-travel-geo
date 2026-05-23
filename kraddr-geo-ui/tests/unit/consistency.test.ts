import { describe, expect, it } from "vitest";
import { severityClass, severityRank } from "@/lib/consistency";

describe("consistency helpers", () => {
  it("severity 순서와 시각 상태를 고정한다", () => {
    expect(severityRank("OK")).toBeLessThan(severityRank("WARN"));
    expect(severityRank("WARN")).toBeLessThan(severityRank("ERROR"));
    expect(severityClass("ERROR")).toBe("error");
    expect(severityClass("WARN")).toBe("warn");
    expect(severityClass("INFO")).toBe("ok");
    expect(severityClass("failed")).toBe("error");
    expect(severityClass("cancelled")).toBe("warn");
  });
});
