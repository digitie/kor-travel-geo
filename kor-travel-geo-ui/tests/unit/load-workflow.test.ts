import { describe, expect, it } from "vitest";
import { confirmationTokenFor, loadWorkflowReducer, percent } from "@/lib/load-workflow";

describe("loadWorkflowReducer", () => {
  it("업로드와 처리 단계를 순서대로 전이한다", () => {
    let state = loadWorkflowReducer("idle", { type: "upload_start" });
    expect(state).toBe("uploading");
    state = loadWorkflowReducer(state, { type: "upload_done" });
    expect(state).toBe("source_review");
    state = loadWorkflowReducer(state, { type: "plan_ready" });
    expect(state).toBe("plan_ready");
    state = loadWorkflowReducer(state, { type: "process_start" });
    expect(state).toBe("processing");
    state = loadWorkflowReducer(state, { type: "finish" });
    expect(state).toBe("finished");
  });

  it("처리 중 업로드 완료 이벤트는 상태를 흔들지 않는다", () => {
    expect(loadWorkflowReducer("processing", { type: "upload_done" })).toBe("processing");
  });

  it("혼합 기준월 확인 문구를 서버 규칙과 같은 형태로 만든다", () => {
    expect(
      confirmationTokenFor({
        juso: "202603",
        parcel_link: "202603",
        locsum: "202604",
        roadaddr_entrance: "202605"
      })
    ).toBe("202603/202604/202605 혼합 적재 확인");
    expect(confirmationTokenFor({ juso: "202603", locsum: "202603" })).toBeNull();
  });

  it("진행률은 0부터 100 사이로 제한한다", () => {
    expect(percent(5, 10)).toBe(50);
    expect(percent(15, 10)).toBe(100);
    expect(percent(1, 0)).toBe(0);
  });
});
