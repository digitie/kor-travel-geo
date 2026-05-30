import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { useConsistencyAnalysisStore } from "@/lib/stores/consistency-analysis-store";

const apiMocks = vi.hoisted(() => ({
  patchJson: vi.fn(),
  postJson: vi.fn(),
  requestJson: vi.fn()
}));

const mapMock = vi.hoisted(() => ({
  LazyCoordinateMap: vi.fn(() => <div data-testid="lazy-coordinate-map" />)
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "/api/proxy",
  backendPath: (path: string) => (path.startsWith("/v1") || path.startsWith("/v2") ? path : `/v1${path}`),
  patchJson: apiMocks.patchJson,
  postJson: apiMocks.postJson,
  requestJson: apiMocks.requestJson
}));

vi.mock("@/components/vworld/LazyCoordinateMap", () => ({
  LazyCoordinateMap: mapMock.LazyCoordinateMap
}));

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ConsistencyPanel />
    </QueryClientProvider>
  );
}

function mockConsistencyApi() {
  apiMocks.requestJson.mockImplementation(async (path: string) => {
    if (path === "/admin/consistency") {
      return [
        {
          report_id: "consistency_1",
          scope: "full",
          severity_max: "ERROR",
          source_set: {},
          started_at: "2026-05-30T00:00:00Z",
          finished_at: "2026-05-30T00:01:00Z",
          generated_by: "cli"
        }
      ];
    }
    if (path === "/admin/consistency/case-definitions") {
      return [
        {
          code: "C4",
          name: "출입구 좌표와 건물 polygon 거리 이상치",
          compares: "대표 출입구 좌표와 건물 polygon",
          abnormal_criteria: "출입구와 nearest polygon 거리가 50m를 초과한다.",
          evidence: ["출입구 점", "건물 polygon"],
          likely_causes: ["좌표 원천 이상치"],
          decision_guide: "지도 확인 후 승인 또는 거절",
          threshold: "50m 초과 WARN"
        },
        {
          code: "C5",
          name: "내비 centroid와 건물 polygon centroid 거리 이상치",
          compares: "내비 centroid와 건물 polygon centroid",
          abnormal_criteria: "두 centroid 거리가 임계값을 초과한다.",
          evidence: ["내비 centroid", "건물 polygon"],
          likely_causes: ["좌표 원천 이상치"],
          decision_guide: "지도 확인 후 승인 또는 거절",
          threshold: "WARN"
        }
      ];
    }
    if (path === "/admin/consistency/consistency_1") {
      return {
        report_id: "consistency_1",
        scope: "full",
        severity_max: "ERROR",
        source_set: {},
        started_at: "2026-05-30T00:00:00Z",
        finished_at: "2026-05-30T00:01:00Z",
        generated_by: "cli",
        cases: [
          {
            code: "C4",
            name: "출입구 좌표와 건물 polygon 거리 이상치",
            severity: "ERROR",
            count: 1
          },
          {
            code: "C5",
            name: "내비 centroid와 건물 polygon centroid 거리 이상치",
            severity: "WARN",
            count: 1
          }
        ]
      };
    }
    const summaryMatch = path.match(/\/cases\/(C\d+)\/summary$/);
    if (summaryMatch) {
      return {
        report_id: "consistency_1",
        case_code: summaryMatch[1],
        total: 1,
        by_severity: { ERROR: 1 },
        by_decision: { unreviewed: 1 },
        by_sig_cd: { "41463": 1 },
        distance: { max_m: 100 }
      };
    }
    const samplesMatch = path.match(/\/cases\/(C\d+)\/samples/);
    if (samplesMatch) {
      const caseCode = samplesMatch[1];
      return {
        report_id: "consistency_1",
        case_code: caseCode,
        total: 1,
        page: 1,
        page_size: 50,
        items: [
          {
            sample_id: `sample-${caseCode}`,
            report_id: "consistency_1",
            case_code: caseCode,
            severity: "ERROR",
            sample_rank: 0,
            bd_mgt_sn: "41463114441215800016900000",
            sig_cd: "41463",
            distance_m: 609.42,
            source_kind: "locsum",
            case_metric: {},
            source_snapshot: { distance_m: 609.42 },
            point: { x: 127.163213, y: 37.295898 },
            bbox_4326: {},
            has_polygon: true,
            has_line: false,
            decision_state: "unreviewed",
            created_at: "2026-05-30T00:00:00Z"
          }
        ]
      };
    }
    throw new Error(`unhandled path: ${path}`);
  });
}

beforeEach(() => {
  apiMocks.patchJson.mockReset();
  apiMocks.postJson.mockReset();
  apiMocks.requestJson.mockReset();
  mapMock.LazyCoordinateMap.mockClear();
  useConsistencyAnalysisStore.setState({
    selectedCaseCode: "C4",
    selectedSampleId: null,
    selectedSampleIds: [],
    drawerOpen: false
  });
  mockConsistencyApi();
});

describe("ConsistencyPanel", () => {
  it("샘플을 선택하기 전에는 무거운 지도 컴포넌트를 로드하지 않는다", async () => {
    renderPanel();

    await screen.findByText("consistency_1");
    await screen.findByText("#1");

    expect(screen.getByText("표본 선택 대기")).toBeInTheDocument();
    expect(screen.queryByTestId("lazy-coordinate-map")).not.toBeInTheDocument();
    expect(mapMock.LazyCoordinateMap).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "#1" }));

    await waitFor(() => expect(screen.getByTestId("lazy-coordinate-map")).toBeInTheDocument());
    expect(mapMock.LazyCoordinateMap).toHaveBeenCalledTimes(1);
  });

  // C1~C10 case 이동 시 무한 re-render로 탭이 멈추던 회귀를 막는다.
  // `samples`가 매 렌더마다 새 배열이면 useReactTable auto-reset이 매 렌더 setState를
  // 호출해 무한 루프에 빠진다. 루프가 재발하면 이 테스트는 타임아웃으로 실패한다.
  it("case를 전환해도 멈추지 않고 새 case 샘플을 렌더한다", async () => {
    renderPanel();

    await screen.findByText("consistency_1");
    await screen.findByText("#1");

    const otherCase = await screen.findByRole("button", { name: /C5/ });
    fireEvent.click(otherCase);

    // 전환된 case(C5)의 기준 패널이 갱신되면 메인 스레드가 살아 있는 것이다.
    // (abnormal_criteria 문구는 CriteriaPanel에만 나타나고 선택된 case에 따라 바뀐다.)
    await waitFor(() =>
      expect(screen.getByText("두 centroid 거리가 임계값을 초과한다.")).toBeInTheDocument()
    );
    await screen.findByText("#1");
  });
});
