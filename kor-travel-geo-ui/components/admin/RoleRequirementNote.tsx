import { ShieldCheck } from "lucide-react";
import { roleLabels } from "@/lib/roles";

/**
 * T-226: proactive "필요 역할" note for a danger/admin action. Display-only — the backend
 * `require_role` dependency enforces access; this just tells the operator which role(s) are
 * required so they aren't surprised by a 403.
 */
export function RoleRequirementNote({ roles, note }: { roles: string[]; note?: string }) {
  return (
    <p className="role-note">
      <ShieldCheck size={13} /> 필요 역할: {roleLabels(roles)}
      {note ? <span className="role-note-extra"> · {note}</span> : null}
    </p>
  );
}
