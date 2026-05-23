export type LoadWorkflowState = "idle" | "uploading" | "upload_done" | "processing" | "finished";

export type LoadWorkflowAction =
  | { type: "upload_start" }
  | { type: "upload_done" }
  | { type: "process_start" }
  | { type: "finish" }
  | { type: "reset" };

export function loadWorkflowReducer(
  state: LoadWorkflowState,
  action: LoadWorkflowAction
): LoadWorkflowState {
  switch (action.type) {
    case "upload_start":
      return "uploading";
    case "upload_done":
      return state === "uploading" ? "upload_done" : state;
    case "process_start":
      return state === "upload_done" || state === "idle" ? "processing" : state;
    case "finish":
      return state === "processing" ? "finished" : state;
    case "reset":
      return "idle";
  }
}
