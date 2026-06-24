/** ok=true -> 검증됨, false -> 불일치, null/undefined -> 미검증(legacy/skipped). */
export function inventoryTone(ok: boolean | null | undefined): {
  tone: "ok" | "error" | "warn";
  label: string;
} {
  if (ok === true) return { tone: "ok", label: "검증됨" };
  if (ok === false) return { tone: "error", label: "불일치" };
  return { tone: "warn", label: "미검증" };
}
