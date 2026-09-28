import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { ReverseDebugger } from "@/components/debug/ReverseDebugger";
import { ApiError } from "@/lib/api";

const apiMocks = vi.hoisted(() => ({ postPublicJson: vi.fn() }));

// ApiError/getErrorMessage/apiErrorResult는 실제 구현을 써서 envelope 파싱까지 함께 검증한다.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postPublicJson: apiMocks.postPublicJson
}));

vi.mock("@/components/vworld/LazyCoordinateMap", () => ({
  LazyCoordinateMap: () => <div data-testid="map" />
}));

// T-309: 2026-09-28에는 statement_timeout이 "KTG_PG_DSN 확인" 503으로 보였다. 이제 504 +
// E0504 envelope를 코드·힌트가 있는 한국어 알림으로 보여 준다.
const TIMEOUT_ENVELOPE = {
  status: "ERROR",
  query_id: "q-1",
  error: {
    code: "E0504",
    message: "database query timed out",
    hint: "the query exceeded the DB statement timeout (KTG_PG_STATEMENT_TIMEOUT_MS)"
  }
};

describe("디버그 화면 오류 표시 (T-309)", () => {
  beforeEach(() => {
    apiMocks.postPublicJson.mockReset();
    apiMocks.postPublicJson.mockRejectedValue(new ApiError(504, JSON.stringify(TIMEOUT_ENVELOPE)));
  });

  it("Geocode는 v2 오류 envelope를 코드·힌트가 담긴 알림으로 표시한다", async () => {
    render(<GeocodeDebugger />);

    fireEvent.click(screen.getByRole("button", { name: "실행" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("DB 쿼리 시간 초과 [E0504]: database query timed out");
    expect(alert).toHaveTextContent("힌트: the query exceeded the DB statement timeout");
    // 원본 envelope는 JSON 패널에 그대로 남는다.
    expect(screen.getByText(/"query_id"/)).toBeInTheDocument();
  });

  it("Reverse도 같은 방식으로 표시한다", async () => {
    render(<ReverseDebugger />);

    fireEvent.click(screen.getByRole("button", { name: "조회" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("DB 쿼리 시간 초과 [E0504]");
  });

  it("성공 응답에는 오류 알림을 띄우지 않는다", async () => {
    apiMocks.postPublicJson.mockResolvedValue({ status: "OK", query_id: "q", candidates: [] });
    render(<GeocodeDebugger />);

    fireEvent.click(screen.getByRole("button", { name: "실행" }));

    expect(await screen.findByText(/"OK"/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
