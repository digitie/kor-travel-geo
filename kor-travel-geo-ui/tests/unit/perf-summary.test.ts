import { describe, expect, it } from "vitest";
import type { OpsArtifact } from "@/lib/api";
import { deltaTone, summarizeBenchmarkArtifacts } from "@/lib/perf-summary";

function benchmark(over: Partial<OpsArtifact> & { artifact_id: string }): OpsArtifact {
  return {
    artifact_type: "benchmark",
    state: "available",
    storage_kind: "local_file",
    created_at: "2026-06-16T00:00:00Z",
    ...over
  } as OpsArtifact;
}

describe("summarizeBenchmarkArtifacts (T-222)", () => {
  it("groups by kind/profile and computes latest-vs-previous deltas", () => {
    const rows = summarizeBenchmarkArtifacts([
      benchmark({
        artifact_id: "b-old",
        manifest: {
          kind: "load_matrix",
          profile: "actual_mix/steady",
          captured_at: "2026-06-15T00:00:00Z",
          metrics: { p95_ms: 10, p99_ms: 20, error_rate: 0, qps: 500 }
        }
      }),
      benchmark({
        artifact_id: "b-new",
        manifest: {
          kind: "load_matrix",
          profile: "actual_mix/steady",
          captured_at: "2026-06-16T00:00:00Z",
          metrics: { p95_ms: 12, p99_ms: 18, error_rate: 0, qps: 540 }
        }
      })
    ]);

    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row.latestArtifactId).toBe("b-new");
    expect(row.baselineArtifactId).toBe("b-old");
    expect(row.latest.p95_ms).toBe(12);
    expect(row.deltas.p95_ms).toBe(2); // 12 - 10 (regression)
    expect(row.deltas.p99_ms).toBe(-2); // 18 - 20 (improvement)
    expect(row.deltas.qps).toBe(40);
  });

  it("prefers an explicit baseline_artifact_id over the previous run", () => {
    const rows = summarizeBenchmarkArtifacts([
      benchmark({
        artifact_id: "base",
        manifest: { kind: "sql", captured_at: "2026-06-10T00:00:00Z", metrics: { p99_ms: 100 } }
      }),
      benchmark({
        artifact_id: "mid",
        manifest: { kind: "sql", captured_at: "2026-06-12T00:00:00Z", metrics: { p99_ms: 50 } }
      }),
      benchmark({
        artifact_id: "cur",
        manifest: {
          kind: "sql",
          captured_at: "2026-06-16T00:00:00Z",
          baseline_artifact_id: "base",
          metrics: { p99_ms: 90 }
        }
      })
    ]);
    const row = rows[0];
    expect(row.latestArtifactId).toBe("cur");
    expect(row.baselineArtifactId).toBe("base"); // explicit, not the more-recent "mid"
    expect(row.deltas.p99_ms).toBe(-10); // 90 - 100
  });

  it("is defensive against missing/empty manifest and metrics", () => {
    const rows = summarizeBenchmarkArtifacts([
      benchmark({ artifact_id: "x" }), // no manifest at all
      benchmark({ artifact_id: "y", manifest: { kind: "rest" } }) // no metrics
    ]);
    expect(rows).toHaveLength(2);
    const other = rows.find((r) => r.kind === "other");
    expect(other?.latest.p95_ms).toBeNull();
    expect(other?.baseline).toBeNull();
    expect(other?.deltas).toEqual({});
  });

  it("deltaTone: lower-is-better for latency, higher-is-better for qps", () => {
    expect(deltaTone("p95_ms", -3)).toBe("ok");
    expect(deltaTone("p95_ms", 3)).toBe("warn");
    expect(deltaTone("error_rate", 0.01)).toBe("warn");
    expect(deltaTone("qps", 50)).toBe("ok");
    expect(deltaTone("qps", -50)).toBe("warn");
    expect(deltaTone("p99_ms", 0)).toBe("neutral");
  });
});
