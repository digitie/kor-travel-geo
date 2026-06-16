import { describe, expect, it } from "vitest";
import {
  estimateEtaSeconds,
  formatEta,
  latestLogLine,
  progressPercent
} from "@/lib/job-progress";

describe("job-progress helpers (T-251)", () => {
  it("estimates remaining seconds from elapsed time and progress", () => {
    const started = "2026-06-16T00:00:00Z";
    const now = Date.parse(started) + 100_000; // 100s elapsed
    // at 50% in 100s → ~100s remaining
    expect(estimateEtaSeconds(started, 0.5, now)).toBe(100);
    // at 80% in 100s → ~25s remaining
    expect(estimateEtaSeconds(started, 0.8, now)).toBe(25);
  });

  it("returns null when it cannot estimate", () => {
    const now = Date.now();
    expect(estimateEtaSeconds(null, 0.5, now)).toBeNull();
    expect(estimateEtaSeconds("2026-06-16T00:00:00Z", 0, now)).toBeNull();
    expect(estimateEtaSeconds("2026-06-16T00:00:00Z", 1, now)).toBeNull();
    expect(estimateEtaSeconds("not-a-date", 0.5, now)).toBeNull();
    // clock skew: now before start → non-positive elapsed
    expect(estimateEtaSeconds("2026-06-16T00:00:00Z", 0.5, Date.parse("2026-06-15T00:00:00Z"))).toBeNull();
    // SSR-safe sentinel: nowMs===0 (clock not yet initialized client-side) → no estimate (issue #256 M2).
    expect(estimateEtaSeconds("2026-06-16T00:00:00Z", 0.5, 0)).toBeNull();
  });

  it("formats ETA across magnitudes", () => {
    expect(formatEta(null)).toBe("—");
    expect(formatEta(45)).toBe("~45s");
    expect(formatEta(90)).toBe("~1m 30s");
    expect(formatEta(3700)).toBe("~1h 1m");
  });

  it("reads the latest log line and clamps percent", () => {
    expect(latestLogLine({ log_tail: undefined })).toBeNull();
    expect(latestLogLine({ log_tail: [] })).toBeNull();
    expect(latestLogLine({ log_tail: ["a", "b"] })).toBe("b");
    expect(progressPercent(0.456)).toBe(46);
    expect(progressPercent(-0.1)).toBe(0);
    expect(progressPercent(1.5)).toBe(100);
  });
});
