import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { CandidateAddressSummary } from "@/components/debug/CandidateAddressSummary";
import { ApiError, postPublicJson } from "@/lib/api";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  postPublicJson: vi.fn()
}));
vi.mock("@/lib/vworld-key", () => ({ useVWorldApiKey: () => ({ apiKey: "" }) }));
vi.mock("@/components/vworld/LazyCoordinateMap", () => ({
  LazyCoordinateMap: ({ point }: { point: unknown }) => <div data-testid="map-point">{JSON.stringify(point)}</div>
}));

const post = vi.mocked(postPublicJson);
const candidate = {
  address: { type: "road", road_address: "서울특별시 강남구 테헤란로 152" },
  point: { lon: 127.036, lat: 37.501 },
  geometry_error: { code: "statement_timeout", retryable: true }
};
const partial = { status: "OK", candidates: [candidate] };

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => { post.mockReset(); });
afterEach(() => { vi.restoreAllMocks(); });

describe("지오코딩 부분 결과와 요청 수명", () => {
  it("도형 timeout 경고와 확인된 좌표를 함께 표시하고 다음 실행으로 복구한다", async () => {
    post.mockResolvedValueOnce(partial).mockResolvedValueOnce({
      status: "OK", candidates: [{ ...candidate, geometry_error: null }]
    });
    render(<GeocodeDebugger />);
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(await screen.findByRole("status", { name: "도형 조회 경고" })).toHaveTextContent("일부 도형 조회 시간이 초과");
    expect(screen.getByTestId("map-point")).toHaveTextContent('{"x":127.036,"y":37.501}');
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    await act(async () => {});
    expect(screen.queryByRole("status", { name: "도형 조회 경고" })).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("주소 문자열이 없어도 typed 부분 실패를 숨기지 않는다", () => {
    render(<CandidateAddressSummary candidates={[{ geometry_error: candidate.geometry_error }]} />);
    expect(screen.getByRole("status", { name: "도형 조회 경고" })).toHaveTextContent("확인된 좌표");
  });

  it("취소 버튼은 fetch signal을 취소하고 늦은 결과를 채택하지 않으며 재실행할 수 있다", async () => {
    const first = deferred(); post.mockReturnValueOnce(first.promise).mockResolvedValueOnce(partial);
    render(<GeocodeDebugger />);
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    const signal = post.mock.calls[0][3];
    expect(signal).toBeInstanceOf(AbortSignal);
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(signal?.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "실행" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("요청을 취소했습니다");
    await act(async () => first.resolve(partial));
    expect(screen.getByTestId("map-point")).toHaveTextContent("null");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(await screen.findByRole("status", { name: "도형 조회 경고" })).toBeInTheDocument();
  });

  it("새 제출은 이전 요청을 취소하고 오래된 응답과 finally가 새 요청을 덮지 않는다", async () => {
    const first = deferred(), second = deferred();
    post.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { container } = render(<GeocodeDebugger />);
    const form = container.querySelector("form")!;
    fireEvent.submit(form); const signal = post.mock.calls[0][3];
    fireEvent.submit(form);
    expect(signal?.aborted).toBe(true);
    await act(async () => first.resolve(partial));
    expect(screen.getByRole("button", { name: "실행" })).toBeDisabled();
    expect(screen.getByTestId("map-point")).toHaveTextContent("null");
    await act(async () => second.resolve({ status: "OK", candidates: [{ point: { lon: 128, lat: 38 } }] }));
    expect(screen.getByTestId("map-point")).toHaveTextContent('{"x":128,"y":38}');
    expect(screen.getByRole("button", { name: "실행" })).toBeEnabled();
  });

  it("화면 이탈은 요청을 취소하고 취소를 무시한 늦은 실패를 표시하지 않는다", async () => {
    const pending = deferred(); post.mockReturnValue(pending.promise);
    const { unmount } = render(<GeocodeDebugger />);
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    const signal = post.mock.calls[0][3];
    unmount(); expect(signal?.aborted).toBe(true);
    await act(async () => pending.reject(new Error("late-error")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("primary HTTP 실패를 부분 성공으로 바꾸지 않는다", async () => {
    post.mockRejectedValue(new ApiError(504, JSON.stringify({ status: "ERROR", error: { code: "E0504", message: "primary timeout" } })));
    render(<GeocodeDebugger />);
    fireEvent.click(screen.getByRole("button", { name: "실행" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("E0504");
    expect(screen.queryByRole("status", { name: "도형 조회 경고" })).not.toBeInTheDocument();
    expect(screen.getByTestId("map-point")).toHaveTextContent("null");
  });
});
