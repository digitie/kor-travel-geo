export type LoadWorkflowState =
  | "idle"
  | "uploading"
  | "source_review"
  | "plan_ready"
  | "processing"
  | "finished"
  | "cancelled"
  | "failed";

export type LoadWorkflowAction =
  | { type: "upload_start" }
  | { type: "upload_done" }
  | { type: "plan_ready" }
  | { type: "process_start" }
  | { type: "finish" }
  | { type: "cancel" }
  | { type: "fail" }
  | { type: "reset" };

export function loadWorkflowReducer(
  state: LoadWorkflowState,
  action: LoadWorkflowAction
): LoadWorkflowState {
  switch (action.type) {
    case "upload_start":
      return "uploading";
    case "upload_done":
      return state === "uploading" ? "source_review" : state;
    case "plan_ready":
      return state === "source_review" || state === "uploading" ? "plan_ready" : state;
    case "process_start":
      return state === "plan_ready" || state === "source_review" ? "processing" : state;
    case "finish":
      return state === "processing" ? "finished" : state;
    case "cancel":
      return "cancelled";
    case "fail":
      return "failed";
    case "reset":
      return "idle";
  }
}

export function confirmationTokenFor(
  versions: Record<string, string | null | undefined>
): string | null {
  const months = Array.from(
    new Set(Object.values(versions).filter((value): value is string => Boolean(value)))
  ).sort();
  return months.length > 1 ? `${months.join("/")} 혼합 적재 확인` : null;
}

export function percent(uploaded: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((uploaded / total) * 100)));
}
