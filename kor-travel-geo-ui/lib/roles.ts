/**
 * T-226: admin role labels + required-role guidance for danger actions.
 *
 * Mirrors the backend `api/security.py` ROLE_* constants. The backend `require_role`
 * dependency is the authoritative gate — these labels are display-only operator guidance
 * shown proactively next to high-risk actions so an operator knows the role they need
 * before attempting (and before hitting a 403).
 */
export const KNOWN_ADMIN_ROLES = [
  "source_file_viewer",
  "source_file_manager",
  "rebuild_operator",
  "destructive_admin"
] as const;

export type AdminRole = (typeof KNOWN_ADMIN_ROLES)[number];

const ADMIN_ROLE_LABELS: Record<AdminRole, string> = {
  source_file_viewer: "원천 파일 조회",
  source_file_manager: "원천 파일 관리",
  rebuild_operator: "DB 재구성 운영",
  destructive_admin: "파괴적 작업 관리"
};

export function roleLabel(role: string): string {
  const label = (ADMIN_ROLE_LABELS as Record<string, string>)[role];
  return label ? `${role} (${label})` : role;
}

export function roleLabels(roles: string[]): string {
  return roles.map(roleLabel).join(" + ");
}
