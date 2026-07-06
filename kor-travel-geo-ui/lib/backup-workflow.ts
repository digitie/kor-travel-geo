import { API_BASE, backendPath } from "@/lib/api";

export type BackupPhase =
  | "preflight"
  | "dump"
  | "archive"
  | "checksum"
  | "extract"
  | "restore"
  | "analyze"
  | "validate"
  | "finalize";

export function backupDownloadHref(downloadUrl?: string | null): string | null {
  if (!downloadUrl) return null;
  if (/^https?:\/\//.test(downloadUrl)) return downloadUrl;
  return `${API_BASE}${backendPath(downloadUrl)}`;
}

export function shaPrefix(value?: string | null, length = 12): string {
  if (!value) return "-";
  return value.slice(0, Math.max(1, Math.min(length, value.length)));
}

export function terminalJobState(state: string): boolean {
  return state === "done" || state === "failed" || state === "cancelled";
}

export function stagePhase(stage?: string | null): BackupPhase | "unknown" {
  const normalized = (stage ?? "").toLowerCase();
  if (normalized.includes("preflight")) return "preflight";
  if (normalized.includes("dump")) return "dump";
  if (normalized.includes("archive")) return "archive";
  if (normalized.includes("checksum")) return "checksum";
  if (normalized.includes("extract")) return "extract";
  if (normalized.includes("restore")) return "restore";
  if (normalized.includes("analyze")) return "analyze";
  if (normalized.includes("validate")) return "validate";
  if (normalized.includes("finalize")) return "finalize";
  return "unknown";
}

export function backupProfileLabel(profile?: unknown): string {
  if (profile === "serving-ready") return "serving-ready";
  if (profile === "lean-serving") return "lean-serving";
  if (profile === "forensic") return "forensic";
  return "-";
}

/** 백업 프로파일별 한 줄 설명 — 폼 선택지/도움말에서 사용한다. */
export const backupProfileDescriptions: Record<string, string> = {
  "serving-ready": "서빙에 필요한 전체 구성 — 복원 후 바로 운영 가능 (기본)",
  "lean-serving": "서빙 최소 구성 — 용량이 작지만 일부 보조 데이터 제외",
  forensic: "원본 보존용 전체 백업 — 가장 크고 가장 완전함"
};
