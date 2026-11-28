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

export type DagsterRunAction = components["schemas"]["DagsterRunActionRequest"]["action"];

export const dagsterPaths = {
  summary: "/ops/dagster/summary",
  runDetail: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}`,
  runFailures: "/ops/dagster/run-failures",
  runFailureAck: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}/ack`,
  runAction: (runId: string) => `/ops/dagster/runs/${encodeURIComponent(runId)}/action`
};

export function useDagsterSummaryQuery() {
  return useQuery({
    queryKey: ["dagster", "summary"],
    queryFn: async ({ signal }) => {
      const response = await requestJson<DagsterSummaryResponse>(dagsterPaths.summary, { signal: AbortSignal.any([signal, AbortSignal.timeout(25_000)]) });
      if (response.data.status !== "ok") {
        throw new Error(`Dagster 상태: ${response.data.status} · ${response.data.errors?.join(" / ") || "조회 결과를 확인하지 못했습니다."}`);
      }
      return response;
    },
    retry: false,
    refetchInterval: 30_000
  });
}

export function useDagsterRunDetailQuery(runId: string | null, after: string | null = null) {
  return useQuery({
    queryKey: ["dagster", "run", runId, after],
    queryFn: ({ signal }) => {
      const path = dagsterPaths.runDetail(runId ?? "");
      return requestJson<DagsterRunDetailResponse>(
        after ? `${path}?after=${encodeURIComponent(after)}` : path,
        { signal: AbortSignal.any([signal, AbortSignal.timeout(25_000)]) }
      );
    },
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: query => {
      const status = query.state.data?.data.run?.status;
      return status && ["SUCCESS", "FAILURE", "CANCELED"].includes(status) ? false : 15_000;
    }
  });
}

export function useDagsterRunFailuresQuery() {
  return useQuery({
    queryKey: ["dagster", "run-failures"],
    queryFn: ({ signal }) => requestJson<DagsterRunFailuresResponse>(dagsterPaths.runFailures, { signal: AbortSignal.any([signal, AbortSignal.timeout(25_000)]) }),
    retry: false,
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

export function useDagsterRunActionMutation(onReexecuted: (runId: string) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, action }: { runId: string; action: DagsterRunAction }) =>
      postJson<components["schemas"]["DagsterRunActionResponse"]>(dagsterPaths.runAction(runId), { action }),
    retry: false,
    onSuccess: (result) => {
      toast.success(result.action === "force-cancel" ? "즉시 취소를 요청했습니다." : "재실행을 접수했습니다.");
      if (result.action === "reexecute") onReexecuted(result.run_id);
    },
    onError: (error) => {
      toast.error("Dagster 실행 제어 실패", getErrorMessage(error));
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["dagster"] })
  });
}

export function formatDagsterEpoch(value: number | string | null | undefined): string {
  // Run and tick timestamps use epoch seconds.
  const epoch = typeof value === "string" ? Number(value) : value;
  if (epoch == null || !Number.isFinite(epoch)) return "-";
  return new Date(epoch * 1000).toISOString().slice(0, 19).replace("T", " ");
}

// GraphQL event timestamps use epoch milliseconds, unlike run and tick times.
export function formatDagsterEventTime(value: string | null | undefined): string {
  if (value == null || value.trim() === "") return "-";
  return formatDagsterEpoch(Number(value) / 1000);
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
