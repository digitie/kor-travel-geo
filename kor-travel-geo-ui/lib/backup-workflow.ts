import { API_BASE, backendPath, type DbLifecycleCapabilities } from "@/lib/api";

/** T-312: 공용 DB instance에서 막힌 DB 수명주기 기능(복원·hot-swap·restore drill) 안내 문구. */
export const DB_LIFECYCLE_UNSUPPORTED_TEXT =
  "공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행";

/**
 * T-321: 공용 instance에서도 되는 복원 경로(backend E0410 hint와 같은 절차). 이 화면은 DSN
 * 자격증명을 받지 않는다 — target_dsn은 job payload·Dagster run config에 그대로 남기 때문이다.
 */
export const DB_RESTORE_SHARED_INSTANCE_TEXT =
  "공용 instance 복원 절차: cluster admin이 app role 소유의 빈 DB(x_extension·extension 사전 구성)를 " +
  "만든 뒤 운영자가 그 DB를 가리키는 target_dsn으로 복원한다(ktgctl restore create --target-dsn). " +
  "이 화면은 DSN 자격증명을 받지 않는다 — docs/t046-db-backup-restore.md '공용 DB instance'";

/**
 * T-312: 연결 DB role이 DB 수명주기 기능을 실행할 수 없는지. capability를 아직 못 읽었거나
 * 조회에 실패하면(null) 막지 않는다 — backend가 E0410으로 최종 거절한다.
 */
export function dbLifecycleBlocked(
  capabilities: DbLifecycleCapabilities | null | undefined
): capabilities is DbLifecycleCapabilities {
  return capabilities?.supported === false;
}

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
