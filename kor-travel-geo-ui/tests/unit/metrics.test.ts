import { describe, expect, it } from "vitest";
import {
  backendRouteForMetrics,
  normalizeMetricRoute,
  recordProxyUpstream,
  recordUiRequest,
  recordWebVital,
  renderPrometheusMetrics
} from "@/lib/metrics";

describe("Prometheus metrics", () => {
  it("동적 route segment를 낮은 cardinality label로 정규화한다", () => {
    expect(normalizeMetricRoute("/v1/admin/loads/12345")).toBe("/v1/admin/loads/:id");
    expect(
      backendRouteForMetrics([
        "v2",
        "geocode",
        "550e8400-e29b-41d4-a716-446655440000"
      ])
    ).toBe("/v2/geocode/:id");
  });

  it("UI request, proxy upstream, Web Vitals metric을 Prometheus text로 렌더링한다", () => {
    recordUiRequest({
      method: "GET",
      route: "/api/runtime-config",
      statusCode: 200,
      elapsedSeconds: 0.012
    });
    recordProxyUpstream({
      method: "POST",
      backendRoute: "/v2/geocode",
      statusCode: 200,
      elapsedSeconds: 0.05
    });
    recordWebVital({
      name: "LCP",
      route: "/admin/load",
      rating: "good",
      value: 1200
    });

    const body = renderPrometheusMetrics();

    expect(body).toContain("kor_travel_geo_ui_http_requests_total");
    expect(body).toContain("kor_travel_geo_ui_http_request_duration_seconds_bucket");
    expect(body).toContain("kor_travel_geo_ui_proxy_upstream_request_duration_seconds_bucket");
    expect(body).toContain("kor_travel_geo_ui_web_vitals_total");
    expect(body).toContain("kor_travel_geo_ui_web_vital_value_bucket");
    expect(body).toContain('route="/api/runtime-config"');
    expect(body).toContain('backend_route="/v2/geocode"');
    expect(body).toContain('name="LCP"');
  });
});
