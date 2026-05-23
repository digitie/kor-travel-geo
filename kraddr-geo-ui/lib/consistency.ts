export const severityOrder = { OK: 0, INFO: 1, WARN: 2, ERROR: 3 } as const;

export function severityClass(value: string): "ok" | "warn" | "error" {
  const normalized = value.toUpperCase();
  if (normalized === "ERROR" || normalized === "FAILED") return "error";
  if (normalized === "WARN" || normalized === "CANCELLED") return "warn";
  return "ok";
}

export function severityRank(value: keyof typeof severityOrder): number {
  return severityOrder[value];
}
