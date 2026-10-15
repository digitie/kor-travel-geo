import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDagsterRunDetailQuery, useDagsterSummaryQuery } from "@/lib/dagster";

const api = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("@/lib/api", () => ({
  requestJson: api.requestJson, getErrorMessage: String, postJson: vi.fn()
}));

function Wrapper({ children }: { children: ReactNode }) {
  // 운영 공통 기본값이 retry를 허용해도 이 조회들은 즉시 재시도하지 않는다.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 2, gcTime: 0 } } }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function advance(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

describe("Dagster 조회 주기와 실패 격리", () => {
  beforeEach(() => { vi.useFakeTimers(); api.requestJson.mockReset(); });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it("선택 전에는 상세 요청을 보내지 않는다", async () => {
    renderHook(() => useDagsterRunDetailQuery(null), { wrapper: Wrapper });
    await advance(31_000);
    expect(api.requestJson).not.toHaveBeenCalled();
  });

  it.each(["SUCCESS", "FAILURE", "CANCELED"])("%s 실행은 자동 상세 조회를 멈추지만 수동 갱신할 수 있다", async status => {
    api.requestJson.mockResolvedValue({ data: { status: "ok", run: { status } } });
    const { result } = renderHook(() => useDagsterRunDetailQuery("run-1"), { wrapper: Wrapper });
    await advance(1);
    await advance(31_000);
    expect(api.requestJson).toHaveBeenCalledTimes(1);
    await act(async () => { await result.current.refetch(); });
    expect(api.requestJson).toHaveBeenCalledTimes(2);
  });

  it("활성 실행은 기존 15초 주기로 갱신하고 종료 후 멈춘다", async () => {
    api.requestJson.mockResolvedValueOnce({ data: { status: "ok", run: { status: "STARTED" } } })
      .mockResolvedValue({ data: { status: "ok", run: { status: "SUCCESS" } } });
    renderHook(() => useDagsterRunDetailQuery("run-1"), { wrapper: Wrapper });
    await advance(1);
    await advance(15_000);
    expect(api.requestJson).toHaveBeenCalledTimes(2);
    await advance(31_000);
    expect(api.requestJson).toHaveBeenCalledTimes(2);
  });

  it("상세 장애는 즉시 재시도하지 않고 다음 주기에 복구한다", async () => {
    api.requestJson.mockRejectedValueOnce(new Error("temporary unavailable"))
      .mockResolvedValue({ data: { status: "ok", run: { status: "SUCCESS" } } });
    const { result } = renderHook(() => useDagsterRunDetailQuery("run-1"), { wrapper: Wrapper });
    await advance(5_000);
    expect(api.requestJson).toHaveBeenCalledTimes(1);
    expect(result.current.isError).toBe(true);
    await advance(15_000);
    expect(api.requestJson).toHaveBeenCalledTimes(2);
    expect(result.current.isSuccess).toBe(true);
  });

  it("요약의 unavailable은 오류로 표시하고 즉시 반복하지 않으며 다음 주기에 복구한다", async () => {
    api.requestJson.mockResolvedValueOnce({ data: { status: "unavailable", errors: ["timeout"] } })
      .mockResolvedValue({ data: { status: "ok" } });
    const { result } = renderHook(() => useDagsterSummaryQuery(), { wrapper: Wrapper });
    await advance(5_000);
    expect(api.requestJson).toHaveBeenCalledTimes(1);
    expect(result.current.isError).toBe(true);
    await advance(30_000);
    expect(api.requestJson).toHaveBeenCalledTimes(2);
    expect(result.current.isSuccess).toBe(true);
  });

  it("선택을 바꾸면 이전 상세 신호를 취소한다", async () => {
    api.requestJson.mockImplementation((_path: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    }));
    const { rerender } = renderHook(({ runId }) => useDagsterRunDetailQuery(runId), {
      initialProps: { runId: "run-old" }, wrapper: Wrapper
    });
    await advance(1);
    const oldSignal = api.requestJson.mock.calls[0][1].signal as AbortSignal;
    rerender({ runId: "run-new" });
    await advance(1);
    expect(oldSignal.aborted).toBe(true);
    expect(api.requestJson.mock.calls[1][0]).toBe("/ops/dagster/runs/run-new");
  });
});
