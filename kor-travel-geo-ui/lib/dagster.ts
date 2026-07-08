"use client";

import { useQuery } from "@tanstack/react-query";

import { requestJson } from "@/lib/api";
import type { components } from "@/types/api.gen";

export type DagsterAssetGroup = components["schemas"]["DagsterAssetGroup"];
export type DagsterGraphqlError = components["schemas"]["DagsterGraphqlError"];
export type DagsterInstigationTick = components["schemas"]["DagsterInstigationTick"];
export type DagsterRepository = components["schemas"]["DagsterRepository"];
export type DagsterRunDetailData = components["schemas"]["DagsterRunDetailData"];
export type DagsterRunDetailResponse = components["schemas"]["DagsterRunDetailResponse"];
export type DagsterRunEvent = components["schemas"]["DagsterRunEvent"];
export type DagsterRunSummary = components["schemas"]["DagsterRunSummary"];
export type DagsterSchedule = components["schemas"]["DagsterSchedule"];
export type DagsterSensor = components["schemas"]["DagsterSensor"];
export type DagsterSummaryData = components["schemas"]["DagsterSummaryData"];
export type DagsterSummaryResponse = components["schemas"]["DagsterSummaryResponse"];

export const dagsterPaths = {
  summary: "/ops/dagster/summary",
  runDetail: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}`
};

export function useDagsterSummaryQuery() {
  return useQuery({
    queryKey: ["dagster", "summary"],
    queryFn: () => requestJson<DagsterSummaryResponse>(dagsterPaths.summary),
    refetchInterval: 30_000
  });
}

export function useDagsterRunDetailQuery(runId: string | null) {
  return useQuery({
    queryKey: ["dagster", "run", runId],
    queryFn: () => requestJson<DagsterRunDetailResponse>(dagsterPaths.runDetail(runId ?? "")),
    enabled: Boolean(runId),
    refetchInterval: 15_000
  });
}

export function formatDagsterEpoch(value: number | string | null | undefined): string {
  // Run start/end arrive as numbers; event timestamps arrive as numeric epoch
  // strings (DagsterRunEvent.timestamp). Coerce so both render as a UTC date.
  const epoch = typeof value === "string" ? Number(value) : value;
  if (epoch == null || !Number.isFinite(epoch)) return "-";
  return new Date(epoch * 1000).toISOString().slice(0, 19).replace("T", " ");
}

export function dagsterRunUrl(dagsterUrl: string, runId: string): string {
  try {
    const url = new URL(dagsterUrl);
    url.pathname = `${url.pathname.replace(/\/$/, "")}/runs/${encodeURIComponent(runId)}`;
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return dagsterUrl;
  }
}

export function dagsterStatusTone(value: string | null | undefined): "ok" | "warn" | "error" {
  const normalized = (value ?? "").toLowerCase();
  if (
    ["ok", "success", "succeeded", "done", "completed"].some((token) =>
      normalized.includes(token)
    )
  ) {
    return "ok";
  }
  if (
    ["fail", "error", "unavailable", "not_found", "cancel"].some((token) =>
      normalized.includes(token)
    )
  ) {
    return "error";
  }
  return "warn";
}
