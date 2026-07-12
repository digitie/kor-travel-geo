"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getErrorMessage, postJson, requestJson } from "@/lib/api";
import { toast } from "@/lib/toast";
import type { components } from "@/types/api.gen";

export type DagsterAssetGroup = components["schemas"]["DagsterAssetGroup"];
export type DagsterGraphqlError = components["schemas"]["DagsterGraphqlError"];
export type DagsterInstigationTick = components["schemas"]["DagsterInstigationTick"];
export type DagsterRepository = components["schemas"]["DagsterRepository"];
export type DagsterRunDetailData = components["schemas"]["DagsterRunDetailData"];
export type DagsterRunDetailResponse = components["schemas"]["DagsterRunDetailResponse"];
export type DagsterRunEvent = components["schemas"]["DagsterRunEvent"];
export type DagsterRunFailureAlert = components["schemas"]["DagsterRunFailureAlert"];
export type DagsterRunFailuresResponse = components["schemas"]["DagsterRunFailuresResponse"];
export type DagsterRunFailureAckResponse = components["schemas"]["DagsterRunFailureAckResponse"];
export type DagsterRunSummary = components["schemas"]["DagsterRunSummary"];
export type DagsterSchedule = components["schemas"]["DagsterSchedule"];
export type DagsterSensor = components["schemas"]["DagsterSensor"];
export type DagsterSummaryData = components["schemas"]["DagsterSummaryData"];
export type DagsterSummaryResponse = components["schemas"]["DagsterSummaryResponse"];

export const dagsterPaths = {
  summary: "/ops/dagster/summary",
  runDetail: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}`,
  runFailures: "/ops/dagster/run-failures",
  runFailureAck: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}/ack`
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

export function useDagsterRunFailuresQuery() {
  return useQuery({
    queryKey: ["dagster", "run-failures"],
    queryFn: () => requestJson<DagsterRunFailuresResponse>(dagsterPaths.runFailures),
    refetchInterval: 30_000
  });
}

export function useAckRunFailureMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      postJson<DagsterRunFailureAckResponse>(dagsterPaths.runFailureAck(runId), {}),
    onSuccess: () => {
      toast.success("실패 알림을 확인 처리했습니다.");
      void queryClient.invalidateQueries({ queryKey: ["dagster", "run-failures"] });
      void queryClient.invalidateQueries({ queryKey: ["dagster", "run"] });
    },
    onError: (error) => {
      toast.error("실패 알림 확인 실패", getErrorMessage(error));
    }
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
