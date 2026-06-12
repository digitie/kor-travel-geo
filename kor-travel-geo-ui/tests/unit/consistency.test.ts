import { describe, expect, it } from "vitest";
import { consistencySamplesPath, decisionReasons, severityClass, severityRank } from "@/lib/consistency";
import { useConsistencyAnalysisStore } from "@/lib/stores/consistency-analysis-store";

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

  it("sample query path와 decision reason을 안정적으로 만든다", () => {
    const path = consistencySamplesPath({
      reportId: "consistency_1",
      caseCode: "C4",
      severity: "ERROR",
      decision: "unreviewed",
      sigCd: "11110",
      orderBy: "distance_m",
      desc: true,
      page: 2,
      pageSize: 50,
      format: "csv"
    });

    expect(path).toContain("/admin/consistency/consistency_1/cases/C4/samples");
    expect(path).toContain("severity=ERROR");
    expect(path).toContain("decision=unreviewed");
    expect(path).toContain("format=csv");
    expect(decisionReasons.rejected).toContain("loader_key_error");
  });

  it("Zustand store가 case 변경과 sample 다중 선택을 분리한다", () => {
    const store = useConsistencyAnalysisStore.getState();
    store.setSelectedCase("C7");
    store.toggleSample("sample-1");
    store.toggleSample("sample-2");

    expect(useConsistencyAnalysisStore.getState().selectedCaseCode).toBe("C7");
    expect(useConsistencyAnalysisStore.getState().selectedSampleIds).toEqual([
      "sample-1",
      "sample-2"
    ]);

    useConsistencyAnalysisStore.getState().setSelectedCase("C4");
    expect(useConsistencyAnalysisStore.getState().selectedSampleIds).toEqual([]);
  });
});
