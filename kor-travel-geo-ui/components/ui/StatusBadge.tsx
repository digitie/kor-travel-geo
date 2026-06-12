import { severityClass } from "@/lib/consistency";

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status ${severityClass(value)}`}>{value}</span>;
}
