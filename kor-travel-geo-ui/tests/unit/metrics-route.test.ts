import { describe, expect, it } from "vitest";
import { GET } from "@/app/api/metrics/route";
import { POST } from "@/app/api/metrics/web-vitals/route";

describe("Prometheus route handlers", () => {
  it("aggregate scrape returns Prometheus text with no-store", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe(
      "text/plain; version=0.0.4; charset=utf-8"
    );
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).toContain("# HELP ktg_ui_http_requests_total");
  });

  it("rejects non-finite or negative Web Vitals values", async () => {
    const response = await POST(
      new Request("http://ui.test/api/metrics/web-vitals", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: "LCP",
          route: "/admin",
          rating: "good",
          value: -1
        })
      })
    );

    expect(response.status).toBe(400);
  });
});
