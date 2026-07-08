import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DagsterPanel } from "@/components/admin/DagsterPanel";

const apiMocks = vi.hoisted(() => ({
  requestJson: vi.fn()
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    requestJson: apiMocks.requestJson
  };
});

const SUMMARY = {
  data: {
    status: "ok",
    checked_at: "2026-07-08T05:00:00Z",
    dagster_url: "http://127.0.0.1:12703",
    graphql_url: "http://127.0.0.1:12703/graphql",
    version: "1.11.0",
    repository_count: 1,
    job_count: 2,
    schedule_count: 1,
    sensor_count: 1,
    asset_count: 3,
    run_counts: { SUCCESS: 1, FAILURE: 1 },
    errors: [],
    repositories: [
      {
        name: "kortravelgeo",
        location_name: "kortravelgeo_dagster.definitions",
        asset_count: 3,
        jobs: [
          { name: "db_backup_job", is_job: true },
          { name: "mv_refresh_job", is_job: true }
        ],
        schedules: [
          {
            name: "scheduled_backup",
            status: "RUNNING",
            cron_schedule: "0 3 * * *",
            execution_timezone: "Asia/Seoul",
            recent_ticks: [
              {
                tick_id: "tick_1",
                status: "SUCCESS",
                timestamp: 1783483200,
                run_ids: ["run_1"],
                run_keys: []
              }
            ]
          }
        ],
        sensors: [
          {
            name: "run_failure_sensor",
            status: "RUNNING",
            recent_ticks: []
          }
        ],
        asset_groups: [{ group_name: "default", asset_count: 3, assets: ["a", "b", "c"] }]
      }
    ],
    recent_runs: [
      {
        run_id: "run_1",
        job_name: "db_backup_job",
        status: "SUCCESS",
        start_time: 1783483200,
        end_time: 1783483260,
        update_time: 1783483260,
        tags: {}
      },
      {
        run_id: "run_2",
        job_name: "mv_refresh_job",
        status: "FAILURE",
        start_time: 1783483300,
        end_time: 1783483310,
        update_time: 1783483310,
        tags: {}
      }
    ]
  },
  meta: { duration_ms: 8.1 }
};

const RUN_DETAILS = {
  run_1: {
    data: {
      status: "ok",
      checked_at: "2026-07-08T05:00:01Z",
      dagster_url: "http://127.0.0.1:12703",
      graphql_url: "http://127.0.0.1:12703/graphql",
      run: SUMMARY.data.recent_runs[0],
      events: [
        {
          event_type: "STEP_SUCCESS",
          dagster_event_type: "STEP_SUCCESS",
          level: "INFO",
          message: "backup completed",
          step_id: "backup",
          timestamp: "2026-07-08T05:01:00Z"
        }
      ],
      event_cursor: "cursor-1",
      event_has_more: false,
      errors: []
    },
    meta: { duration_ms: 4.2 }
  },
  run_2: {
    data: {
      status: "ok",
      checked_at: "2026-07-08T05:00:02Z",
      dagster_url: "http://127.0.0.1:12703",
      graphql_url: "http://127.0.0.1:12703/graphql",
      run: SUMMARY.data.recent_runs[1],
      events: [
        {
          event_type: "RUN_FAILURE",
          dagster_event_type: "RUN_FAILURE",
          level: "ERROR",
          message: "mv refresh failed",
          step_id: null,
          timestamp: "2026-07-08T05:02:00Z"
        }
      ],
      event_cursor: "cursor-2",
      event_has_more: false,
      errors: []
    },
    meta: { duration_ms: 4.3 }
  }
};

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DagsterPanel />
    </QueryClientProvider>
  );
}

describe("DagsterPanel", () => {
  beforeEach(() => {
    apiMocks.requestJson.mockReset();
  });

  it("요약, 최근 run, iframe을 렌더하고 선택한 run 상세를 조회한다", async () => {
    apiMocks.requestJson.mockImplementation(async (path: string) => {
      if (path === "/ops/dagster/summary") return SUMMARY;
      if (path === "/ops/dagster/runs/run_1") return RUN_DETAILS.run_1;
      if (path === "/ops/dagster/runs/run_2") return RUN_DETAILS.run_2;
      throw new Error(`unhandled path: ${path}`);
    });

    renderPanel();

    expect(await screen.findByText("kortravelgeo_dagster.definitions")).toBeTruthy();
    const iframe = screen.getByTitle("Dagster UI");
    expect(iframe).toHaveAttribute("src", "http://127.0.0.1:12703");
    expect(iframe).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-forms allow-popups allow-downloads"
    );

    await waitFor(() =>
      expect(apiMocks.requestJson).toHaveBeenCalledWith("/ops/dagster/runs/run_1")
    );
    expect(await screen.findByText("STEP_SUCCESS")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "run_2 run 상세" }));
    await waitFor(() =>
      expect(apiMocks.requestJson).toHaveBeenCalledWith("/ops/dagster/runs/run_2")
    );
    expect(await screen.findByText("RUN_FAILURE")).toBeTruthy();
  });

  it("Dagster outage 응답은 오류 배너와 빈 run 상태로 표시한다", async () => {
    apiMocks.requestJson.mockResolvedValue({
      data: {
        ...SUMMARY.data,
        status: "unavailable",
        errors: ["Dagster webserver 연결 실패"],
        recent_runs: [],
        repositories: [],
        repository_count: 0,
        job_count: 0,
        schedule_count: 0,
        sensor_count: 0,
        asset_count: 0,
        run_counts: {}
      },
      meta: { duration_ms: 10 }
    });

    renderPanel();

    expect(await screen.findByText("Dagster 상태: unavailable")).toBeTruthy();
    expect(screen.getByText("Dagster webserver 연결 실패")).toBeTruthy();
    expect(screen.getAllByText("최근 run이 없습니다.").length).toBeGreaterThan(0);
    expect(apiMocks.requestJson).toHaveBeenCalledWith("/ops/dagster/summary");
  });
});
