import { severityClass } from "@/lib/consistency";

export function StatusBadge({
  value,
  tone
}: {
  value: string;
  /** Override the severity-derived colour (e.g. serving-usage badges). */
  tone?: "ok" | "warn" | "error";
}) {
  return <span className={`status ${tone ?? severityClass(value)}`}>{value}</span>;
}
