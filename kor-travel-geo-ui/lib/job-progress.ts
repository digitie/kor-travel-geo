import type { LoadJobStatus } from "@/lib/api";

/**
 * Estimate remaining seconds from elapsed time and fractional progress (T-251).
 * Returns null when it cannot estimate: no start time, non-positive/complete progress,
 * or a clock skew that makes elapsed non-positive.
 */
export function estimateEtaSeconds(
  startedAt: string | null | undefined,
  progress: number,
  nowMs: number
): number | null {
  if (!startedAt) return null;
  if (!(progress > 0) || progress >= 1) return null;
  const startMs = Date.parse(startedAt);
  if (Number.isNaN(startMs)) return null;
  const elapsedMs = nowMs - startMs;
  if (elapsedMs <= 0) return null;
  const remainingMs = (elapsedMs / progress) * (1 - progress);
  return Math.round(remainingMs / 1000);
}

export function formatEta(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `~${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `~${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `~${h}h ${m % 60}m`;
}

/** The newest log line (carries the live byte/stage detail), or null. */
export function latestLogLine(job: Pick<LoadJobStatus, "log_tail">): string | null {
  const tail = job.log_tail;
  if (!tail || tail.length === 0) return null;
  return tail[tail.length - 1] ?? null;
}

/** Clamp a 0..1 progress to an integer percent for display. */
export function progressPercent(progress: number): number {
  return Math.max(0, Math.min(100, Math.round(progress * 100)));
}
