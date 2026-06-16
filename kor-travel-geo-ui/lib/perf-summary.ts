import type { OpsArtifact } from "@/lib/api";

/**
 * T-222: read-only performance/validation summary helpers.
 *
 * benchmark artifacts (T-265, `artifact_type="benchmark"`) carry headline metrics in their
 * manifest. This module turns the raw artifact list into latest-vs-baseline comparison rows
 * (p95/p99/error_rate/qps deltas) per benchmark group, defensively parsing the free-form
 * manifest so an unexpected shape never throws.
 */

export type BenchmarkMetrics = {
  p50_ms?: number | null;
  p95_ms?: number | null;
  p99_ms?: number | null;
  max_ms?: number | null;
  error_rate?: number | null;
  qps?: number | null;
  samples?: number | null;
};

export type BenchmarkSummaryRow = {
  /** Stable group key: `kind/profile`. */
  group: string;
  kind: string;
  profile: string | null;
  workload: string | null;
  phase: string | null;
  latestArtifactId: string;
  latestCapturedAt: string | null;
  storageUri: string | null;
  latest: BenchmarkMetrics;
  /** The compared-against run (explicit baseline_artifact_id if resolvable, else previous run). */
  baseline: BenchmarkMetrics | null;
  baselineArtifactId: string | null;
  /** latest - baseline per metric (only where both are finite numbers). */
  deltas: Partial<Record<keyof BenchmarkMetrics, number>>;
};

const METRIC_KEYS: (keyof BenchmarkMetrics)[] = [
  "p50_ms",
  "p95_ms",
  "p99_ms",
  "max_ms",
  "error_rate",
  "qps",
  "samples"
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function parseMetrics(manifest: Record<string, unknown>): BenchmarkMetrics {
  const raw = asRecord(manifest.metrics);
  const metrics: BenchmarkMetrics = {};
  for (const key of METRIC_KEYS) {
    metrics[key] = asNumber(raw[key]);
  }
  return metrics;
}

function capturedAtOf(artifact: OpsArtifact): string | null {
  const manifest = asRecord(artifact.manifest);
  return asString(manifest.captured_at) ?? artifact.created_at ?? null;
}

/** Sort key: captured_at desc (fallback created_at). Most-recent first. */
function recencyKey(artifact: OpsArtifact): string {
  return capturedAtOf(artifact) ?? "";
}

/**
 * Build latest-vs-baseline comparison rows from benchmark ops artifacts. Artifacts are grouped
 * by `kind/profile`; within a group the most recent run is "latest". The baseline is the run
 * referenced by the latest run's `baseline_artifact_id` when resolvable, otherwise the next
 * most recent run in the same group.
 */
export function summarizeBenchmarkArtifacts(artifacts: OpsArtifact[]): BenchmarkSummaryRow[] {
  const byId = new Map(artifacts.map((a) => [a.artifact_id, a]));
  const groups = new Map<string, OpsArtifact[]>();
  for (const artifact of artifacts) {
    const manifest = asRecord(artifact.manifest);
    const kind = asString(manifest.kind) ?? "other";
    const profile = asString(manifest.profile);
    const group = `${kind}/${profile ?? ""}`;
    const list = groups.get(group);
    if (list) list.push(artifact);
    else groups.set(group, [artifact]);
  }

  const rows: BenchmarkSummaryRow[] = [];
  for (const [group, list] of groups) {
    const sorted = [...list].sort((a, b) => recencyKey(b).localeCompare(recencyKey(a)));
    const latest = sorted[0];
    const latestManifest = asRecord(latest.manifest);
    const latestMetrics = parseMetrics(latestManifest);

    const baselineId = asString(latestManifest.baseline_artifact_id);
    const baselineArtifact =
      (baselineId ? byId.get(baselineId) : undefined) ?? sorted[1] ?? null;
    const baselineMetrics = baselineArtifact ? parseMetrics(asRecord(baselineArtifact.manifest)) : null;

    const deltas: Partial<Record<keyof BenchmarkMetrics, number>> = {};
    if (baselineMetrics) {
      for (const key of METRIC_KEYS) {
        const cur = latestMetrics[key];
        const base = baselineMetrics[key];
        if (typeof cur === "number" && typeof base === "number") {
          deltas[key] = cur - base;
        }
      }
    }

    rows.push({
      group,
      kind: asString(latestManifest.kind) ?? "other",
      profile: asString(latestManifest.profile),
      workload: asString(latestManifest.workload),
      phase: asString(latestManifest.phase),
      latestArtifactId: latest.artifact_id,
      latestCapturedAt: capturedAtOf(latest),
      storageUri: latest.storage_uri ?? null,
      latest: latestMetrics,
      baseline: baselineMetrics,
      baselineArtifactId: baselineArtifact ? baselineArtifact.artifact_id : null,
      deltas
    });
  }

  rows.sort((a, b) => a.group.localeCompare(b.group));
  return rows;
}

/** For latency/error metrics lower is better; for qps/samples higher is better. */
export function deltaTone(
  metric: keyof BenchmarkMetrics,
  delta: number
): "ok" | "warn" | "neutral" {
  if (delta === 0) return "neutral";
  const lowerIsBetter = metric !== "qps" && metric !== "samples";
  const improved = lowerIsBetter ? delta < 0 : delta > 0;
  return improved ? "ok" : "warn";
}
