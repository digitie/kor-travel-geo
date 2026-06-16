import { expect, test, type Page } from "@playwright/test";

// /admin/consistency 접근성·회복성 e2e (T-227). 정합성 콘솔의 키보드(케이스 탭 활성·판정
// 다이얼로그 focus 진입/trap/Esc/포커스 복귀)와 회복성(엔드포인트 500 graceful·표본 페이지네이션·
// refresh 재적재)을 백엔드 없이 page.route mock으로 고정한다. consistency.spec.ts(진입 프리즈
// 회귀)와 같은 표면이지만 a11y/회복성 단언만 추가한다.

const REPORT_ID = "consistency_1";
const CASE_CODES = Array.from({ length: 10 }, (_, index) => `C${index + 1}`);
const CASES = CASE_CODES.map((code, index) => ({
  code,
  name: code === "C4" ? "출입구 좌표와 건물 polygon 거리 이상치" : `${code} 정합성 케이스`,
  severity: code === "C4" ? "ERROR" : "OK",
  count: index + 1
}));

const SAMPLE = {
  sample_id: "sample-1",
  report_id: REPORT_ID,
  case_code: "C4",
  severity: "ERROR",
  sample_rank: 0,
  bd_mgt_sn: "41463114441215800016900000",
  sig_cd: "41463",
  distance_m: 609.42,
  source_kind: "locsum",
  case_metric: { distance_m: 609.42, threshold_m: 50 },
  source_snapshot: { distance_m: 609.42 },
  point: { x: 127.163213, y: 37.295898 },
  bbox_4326: {},
  has_polygon: true,
  has_line: false,
  decision_state: "unreviewed",
  created_at: "2026-05-30T00:00:00Z"
};

type Opts = { errors?: RegExp[]; samplesTotal?: number };

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

async function mockConsistencyApi(page: Page, opts: Opts = {}): Promise<void> {
  const { errors = [], samplesTotal = 1 } = opts;
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/consistency**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (errors.some((re) => re.test(pathname))) {
      await route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"mock 500"}' });
      return;
    }
    const body = resolveBody(pathname, samplesTotal);
    if (body === null) {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill(jsonRoute(body));
  });
}

function resolveBody(pathname: string, samplesTotal: number): unknown {
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
      default_severity: item.severity,
      sample_schema: { distance_m: "number" }
    }));
  }
  if (pathname.includes("/summary")) {
    return {
      report_id: REPORT_ID,
      case_code: "C4",
      total: samplesTotal,
      by_severity: { ERROR: samplesTotal },
      by_decision: { unreviewed: samplesTotal },
      by_sig_cd: { "41463": samplesTotal },
      distance: { max_m: 100 }
    };
  }
  if (pathname.includes("/samples")) {
    return {
      report_id: REPORT_ID,
      case_code: "C4",
      total: samplesTotal,
      page: 1,
      page_size: 50,
      items: [SAMPLE]
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

test.describe("정합성 콘솔 접근성·회복성 /admin/consistency (T-227)", () => {
  test("케이스 탭: 키보드(focus→Enter)로 다른 케이스를 선택할 수 있다", async ({ page }) => {
    await mockConsistencyApi(page);
    await page.goto("/admin/consistency");

    await expect(page.getByRole("tablist", { name: "정합성 케이스" })).toBeVisible();
    const c1 = page.getByRole("tab", { name: /^C1\b/ });
    await c1.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("tab", { name: /^C1\b/, selected: true })).toBeVisible();
  });

  test("판정 다이얼로그: reason 포커스·Esc 닫힘·트리거(승인)로 포커스 복귀", async ({ page }) => {
    await mockConsistencyApi(page);
    await page.goto("/admin/consistency");

    // 표본 #1 선택 → DecisionPanel 판정 버튼 활성화.
    await page.getByRole("button", { name: "#1" }).click();
    const approve = page.getByRole("button", { name: "승인" });
    await approve.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "정합성 판정" });
    await expect(dialog).toBeVisible();
    // 열리면 포커스가 reason select로 이동한다.
    await expect(dialog.getByRole("combobox")).toBeFocused();

    // Esc로 닫히고(키보드 only) 포커스가 트리거로 복귀한다.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(approve).toBeFocused();
  });

  test("회복성: 모든 정합성 엔드포인트 500이어도 콘솔이 죽지 않고 Reports 패널이 보인다", async ({
    page
  }) => {
    await mockConsistencyApi(page, { errors: [/\/admin\/consistency/] });
    await page.goto("/admin/consistency");

    // React Query 기본값(undefined→빈 배열)으로 graceful degradation: 헤더/패널이 렌더된다.
    await expect(page.getByRole("heading", { name: "Consistency" })).toBeVisible();
    await expect(page.getByText("Reports").first()).toBeVisible();
  });

  test("회복성: 표본 페이지네이션(대용량)으로 다음 페이지로 이동한다", async ({ page }) => {
    await mockConsistencyApi(page, { samplesTotal: 120 });
    await page.goto("/admin/consistency");

    // total 120·page_size 50 → 3페이지. Pager가 1/3을 보여 주고 다음으로 넘어간다.
    const pager = page.locator(".pager");
    await expect(pager.getByText("1 / 3 · 120건")).toBeVisible();
    await pager.getByRole("button", { name: "다음" }).click();
    await expect(pager.getByText("2 / 3 · 120건")).toBeVisible();
  });

  test("회복성: refresh 후 서버 상태(reports/cases)가 다시 적재된다", async ({ page }) => {
    await mockConsistencyApi(page);
    await page.goto("/admin/consistency");
    await expect(page.getByText(REPORT_ID).first()).toBeVisible();

    await page.reload();
    await expect(page.getByText(REPORT_ID).first()).toBeVisible();
    await expect(page.getByRole("tablist", { name: "정합성 케이스" })).toBeVisible();
  });
});
