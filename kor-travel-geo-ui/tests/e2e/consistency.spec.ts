import { expect, test, type Page } from "@playwright/test";

// /admin/consistency 진입 프리즈 회귀를 검증한다. 백엔드 API는 page.route로 목킹하므로
// DB 없이 UI 단독으로 실행할 수 있다. 메인 스레드가 멈추면(프리즈) 아래 단언이 타임아웃으로
// 실패하므로, 테스트가 끝까지 진행되는 것 자체가 "멈추지 않음"의 1차 신호다.

const REPORT_ID = "consistency_1";
const CASE_CODES = Array.from({ length: 10 }, (_, index) => `C${index + 1}`);
const CASES = CASE_CODES.map((code, index) => ({
  code,
  name: code === "C4" ? "출입구 좌표와 건물 polygon 거리 이상치" : `${code} 정합성 케이스`,
  severity: code === "C4" ? "ERROR" : "OK",
  count: index + 1
}));

const SAMPLE_WITH_POINT = {
  sample_id: "sample-1",
  report_id: REPORT_ID,
  case_code: "C4",
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
};

async function mockConsistencyApi(page: Page): Promise<void> {
  // VWorld 키 조회는 빈 값으로 고정해 외부 타일 요청을 막는다. 좌표 표시 자체는 키 없이도
  // CoordinateFallback으로 렌더되므로 프리즈 회귀 검증에는 영향이 없다.
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ vworldApiKey: "" })
    });
  });

  await page.route("**/api/proxy/v1/admin/consistency**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = resolveConsistencyBody(pathname);
    if (body === null) {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

function resolveConsistencyBody(pathname: string): unknown {
  if (pathname.endsWith("/admin/consistency")) {
    return [
      {
        report_id: REPORT_ID,
        scope: "full",
        severity_max: "ERROR",
        source_set: {},
        started_at: "2026-05-30T00:00:00Z",
        finished_at: "2026-05-30T00:01:00Z",
        generated_by: "cli"
      }
    ];
  }
  if (pathname.includes("/case-definitions")) {
    return CASES.map((item) => ({
      code: item.code,
      name: item.name,
      compares: "대표 출입구 좌표와 건물 polygon",
      abnormal_criteria: "출입구와 nearest polygon 거리가 50m를 초과한다.",
      evidence: ["출입구 점", "건물 polygon"],
      likely_causes: ["좌표 원천 이상치"],
      decision_guide: "지도 확인 후 승인 또는 거절",
      threshold: "50m 초과 WARN"
    }));
  }
  if (pathname.includes("/summary")) {
    return {
      report_id: REPORT_ID,
      case_code: "C4",
      total: 1,
      by_severity: { ERROR: 1 },
      by_decision: { unreviewed: 1 },
      by_sig_cd: { "41463": 1 },
      distance: { max_m: 100 }
    };
  }
  if (pathname.includes("/samples")) {
    return {
      report_id: REPORT_ID,
      case_code: "C4",
      total: 1,
      page: 1,
      page_size: 50,
      items: [SAMPLE_WITH_POINT]
    };
  }
  if (pathname.endsWith(`/admin/consistency/${REPORT_ID}`)) {
    return {
      report_id: REPORT_ID,
      scope: "full",
      severity_max: "ERROR",
      source_set: {},
      started_at: "2026-05-30T00:00:00Z",
      finished_at: "2026-05-30T00:01:00Z",
      generated_by: "cli",
      cases: CASES
    };
  }
  return null;
}

test.describe("Consistency 분석 콘솔", () => {
  test("진입 시 멈추지 않고 표본 선택 전에는 지도 대신 안내를 보여 준다", async ({ page }) => {
    await mockConsistencyApi(page);

    await page.goto("/admin/consistency");

    // 진입 직후 핵심 UI가 렌더되면 메인 스레드가 멈추지 않은 것이다.
    await expect(page.getByRole("heading", { name: "Consistency" })).toBeVisible();
    await expect(page.getByText(REPORT_ID).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "#1" })).toBeVisible();

    // 표본 선택 전에는 지도 대신 안내 박스만 보인다.
    await expect(page.getByText("표본 선택 대기")).toBeVisible();
  });

  test("C1~C10 선택을 가로 스크롤 탭으로 렌더한다", async ({ page }) => {
    await mockConsistencyApi(page);

    await page.goto("/admin/consistency");

    const tabList = page.getByRole("tablist", { name: "정합성 케이스" });
    await expect(tabList).toBeVisible();
    await expect(page.getByRole("tab", { name: /^C1\b/ })).toHaveCount(1);
    await expect(page.getByRole("tab", { name: /^C10\b/ })).toHaveCount(1);
    await expect(page.getByRole("tab", { selected: true })).toContainText("C4");

    const overflowX = await tabList.evaluate((node) => window.getComputedStyle(node).overflowX);
    expect(overflowX).toBe("auto");
  });

  test("표본을 선택하면 지도 섹션과 범례가 나타난다", async ({ page }) => {
    await mockConsistencyApi(page);

    await page.goto("/admin/consistency");
    await page.getByRole("button", { name: "#1" }).click();

    // 선택 후에는 안내가 사라지고 지도 범례가 표시된다.
    await expect(page.getByText("표본 선택 대기")).toHaveCount(0);
    await expect(page.getByText("분류 C4")).toBeVisible();
    await expect(page.getByText("건물 도형 있음")).toBeVisible();
  });
});
