/** ok=true -> 검증됨, false -> 불일치, null/undefined -> 미검증(legacy/skipped). */
export function inventoryTone(ok: boolean | null | undefined): {
  tone: "ok" | "error" | "warn";
  label: string;
} {
  if (ok === true) return { tone: "ok", label: "검증됨" };
  if (ok === false) return { tone: "error", label: "불일치" };
  return { tone: "warn", label: "미검증" };
}

/** 3상(boolean|null) 판정을 StatusBadge tone/label로 — U+2705/U+274C 이모지 표시 대체. */
export function triState(ok: boolean | null | undefined): {
  tone: "ok" | "error" | "warn";
  label: string;
} {
  if (ok === true) return { tone: "ok", label: "OK" };
  if (ok === false) return { tone: "error", label: "FAIL" };
  return { tone: "warn", label: "—" };
}

/**
 * manifest 중첩 객체 접근 — ManifestViewer/RestoreWizard/RestoreReconcilePanel/BackupsPanel에
 * 3벌 중복돼 있던 nested()/readNested() 헬퍼의 통합판.
 */
export function nestedRecord(
  value: Record<string, unknown> | undefined,
  ...keys: string[]
): Record<string, unknown> | undefined {
  let current: Record<string, unknown> | undefined = value;
  for (const key of keys) {
    const next = current?.[key];
    if (!next || typeof next !== "object") return undefined;
    current = next as Record<string, unknown>;
  }
  return current;
}

/** 문자열이면 그대로, 아니면 undefined (manifest 필드 안전 접근). */
export function textValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
