import { describe, expect, it } from "vitest";
import { ApiError, backendPath } from "@/lib/api";
import { buildProxyRequestInit, buildProxyTarget, forwardedProxyHeaders } from "@/lib/proxy";

describe("backendPath", () => {
  it("백엔드 v1 prefix를 안정적으로 붙인다", () => {
    expect(backendPath("/address/geocode")).toBe("/v1/address/geocode");
    expect(backendPath("admin/tables")).toBe("/v1/admin/tables");
    expect(backendPath("/v1/admin/loads")).toBe("/v1/admin/loads");
  });

  it("API 오류는 status를 보존한다", () => {
    const error = new ApiError(422, "invalid");

    expect(error.status).toBe(422);
    expect(error.message).toBe("invalid");
  });

  it("프록시는 /v1 하위 경로만 허용한다", () => {
    expect(buildProxyTarget(["v1", "admin", "tables"], "", "http://backend")?.pathname).toBe(
      "/v1/admin/tables"
    );
    expect(buildProxyTarget(["openapi.json"], "", "http://backend")).toBeNull();
    expect(buildProxyTarget(["v1", "..", "metrics"], "", "http://backend")).toBeNull();
  });

  it("프록시 헤더는 필요한 값만 전달한다", () => {
    const headers = forwardedProxyHeaders(
      new Headers({
        accept: "application/json",
        authorization: "Bearer secret",
        cookie: "a=b",
        "content-type": "application/json"
      })
    );

    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.has("authorization")).toBe(false);
    expect(headers.has("cookie")).toBe(false);
  });

  it("프록시는 업로드 본문을 메모리 버퍼링 없이 스트림으로 전달한다", () => {
    const body = new ReadableStream<Uint8Array>();
    const init = buildProxyRequestInit("POST", new Headers(), body);

    expect(init.body).toBe(body);
    expect(init.duplex).toBe("half");

    const getInit = buildProxyRequestInit("GET", new Headers(), body);
    expect(getInit.body).toBeUndefined();
    expect(getInit.duplex).toBeUndefined();
  });
});
