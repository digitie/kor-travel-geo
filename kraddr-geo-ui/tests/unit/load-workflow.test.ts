import { describe, expect, it } from "vitest";
import { loadWorkflowReducer } from "@/lib/load-workflow";

describe("loadWorkflowReducer", () => {
  it("업로드와 처리 단계를 순서대로 전이한다", () => {
    let state = loadWorkflowReducer("idle", { type: "upload_start" });
    expect(state).toBe("uploading");
    state = loadWorkflowReducer(state, { type: "upload_done" });
    expect(state).toBe("upload_done");
    state = loadWorkflowReducer(state, { type: "process_start" });
    expect(state).toBe("processing");
    state = loadWorkflowReducer(state, { type: "finish" });
    expect(state).toBe("finished");
  });

  it("처리 중 업로드 완료 이벤트는 상태를 흔들지 않는다", () => {
    expect(loadWorkflowReducer("processing", { type: "upload_done" })).toBe("processing");
  });
});
