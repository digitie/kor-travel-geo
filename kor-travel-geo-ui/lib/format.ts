/** ISO 문자열을 "YYYY-MM-DD HH:MM:SS"로 축약한다 (타임존 변환 없음, 표시 전용). */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  return value.slice(0, 19).replace("T", " ");
}

export function formatMs(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function formatBytes(value?: number | null): string {
  if (value == null) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
