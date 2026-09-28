import { describe, expect, it } from "vitest";
import {
  ApiError,
  apiErrorResult,
  backendPath,
  getErrorMessage,
  parseApiErrorEnvelope,
  resultErrorMessage
} from "@/lib/api";
import {
  buildProxyRequestInit,
  buildProxyTarget,
  filteredResponseHeaders,
  forwardedProxyHeaders,
  liveE2EAdminIdentityFromEnv
} from "@/lib/proxy";

describe("backendPath", () => {
  it("기본 백엔드 v1 prefix를 안정적으로 붙이고 명시 v2 경로는 보존한다", () => {
    expect(backendPath("/address/geocode")).toBe("/v1/address/geocode");
    expect(backendPath("admin/tables")).toBe("/v1/admin/tables");
    expect(backendPath("/v1/admin/loads")).toBe("/v1/admin/loads");
    expect(backendPath("/v2/geocode")).toBe("/v2/geocode");
  });

  it("API 오류는 status를 보존한다", () => {
    const error = new ApiError(422, "invalid");

    expect(error.status).toBe(422);
    expect(error.message).toBe("invalid");
  });

  it("프록시는 /v1 및 /v2 하위 경로만 허용한다", () => {
    expect(buildProxyTarget(["v1", "admin", "tables"], "", "http://backend")?.pathname).toBe(
      "/v1/admin/tables"
    );
    expect(buildProxyTarget(["v2", "geocode"], "", "http://backend")?.pathname).toBe(
      "/v2/geocode"
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
        "content-type": "application/json",
        "x-ktg-actor": "browser-forged",
        "x-ktg-roles": "destructive_admin"
      }),
      {}
    );

    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.has("authorization")).toBe(false);
    expect(headers.has("cookie")).toBe(false);
    expect(headers.has("x-ktg-actor")).toBe(false);
    expect(headers.has("x-ktg-roles")).toBe(false);
  });

  it("응답 프록시는 알려진 안전 헤더만 relay하고 나머지는 버린다 (T-294)", () => {
    const headers = filteredResponseHeaders(
      new Headers({
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
        "retry-after": "3",
        "content-disposition": 'attachment; filename="export.csv"',
        "content-encoding": "gzip",
        "content-length": "1234",
        "set-cookie": "backend-internal=leak",
        "x-request-id": "abc-123"
      })
    );

    expect(headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(headers.get("cache-control")).toBe("no-store");
    expect(headers.get("retry-after")).toBe("3");
    expect(headers.get("content-disposition")).toBe('attachment; filename="export.csv"');
    expect(headers.has("content-encoding")).toBe(false);
    expect(headers.has("content-length")).toBe(false);
    expect(headers.has("set-cookie")).toBe(false);
    expect(headers.has("x-request-id")).toBe(false);
  });

  it("응답에 content-type이 없으면 application/json으로 fallback한다", () => {
    const headers = filteredResponseHeaders(new Headers({ "cache-control": "no-store" }));

    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("cache-control")).toBe("no-store");
  });

  it("live e2e admin proxy opt-in일 때만 신뢰 role 헤더를 주입한다", () => {
    expect(
      liveE2EAdminIdentityFromEnv({
        KTG_LIVE_E2E_ADMIN_ACTOR: "codex",
        KTG_LIVE_E2E_ADMIN_ROLES: "source_file_viewer"
      })
    ).toBeNull();

    const headers = forwardedProxyHeaders(
      new Headers({ accept: "application/json" }),
      {
        KTG_LIVE_E2E_ADMIN_PROXY: "1",
        KTG_LIVE_E2E_ADMIN_ACTOR: " codex-live ",
        KTG_LIVE_E2E_ADMIN_ROLES:
          "source_file_viewer,unknown,rebuild_operator,source_file_viewer"
      }
    );

    expect(headers.get("accept")).toBe("application/json");
    expect(headers.get("x-ktg-actor")).toBe("codex-live");
    expect(headers.get("x-ktg-roles")).toBe("source_file_viewer,rebuild_operator");
  });

  it("live e2e admin proxy는 actor 또는 유효 role이 없으면 주입하지 않는다", () => {
    expect(
      liveE2EAdminIdentityFromEnv({
        KTG_LIVE_E2E_ADMIN_PROXY: "1",
        KTG_LIVE_E2E_ADMIN_ACTOR: "codex",
        KTG_LIVE_E2E_ADMIN_ROLES: "system,unknown"
      })
    ).toBeNull();

    const headers = forwardedProxyHeaders(new Headers(), {
      KTG_LIVE_E2E_ADMIN_PROXY: "true",
      KTG_LIVE_E2E_ADMIN_ACTOR: "   ",
      KTG_LIVE_E2E_ADMIN_ROLES: "source_file_viewer"
    });

    expect(headers.has("x-ktg-actor")).toBe(false);
    expect(headers.has("x-ktg-roles")).toBe(false);
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

  it("프록시는 클라이언트 abort signal을 upstream fetch로 전달한다", () => {
    const controller = new AbortController();
    const init = buildProxyRequestInit("GET", new Headers(), null, controller.signal);
    expect(init.signal).toBe(controller.signal);

    const withoutSignal = buildProxyRequestInit("GET", new Headers(), null);
    expect(withoutSignal.signal).toBeUndefined();
  });
});

// T-309: 2026-09-28 장애 때 디버그 화면은 v2 envelope를 raw JSON 문자열로 보여 줘
// "KTG_PG_DSN 확인" 힌트만 눈에 띄었다. 코드·메시지·힌트를 한 줄로 정규화한다.
const V2_TIMEOUT_BODY = {
  status: "ERROR",
  query_id: "q-1",
  error: {
    code: "E0504",
    message: "database query timed out",
    hint: "the query exceeded the DB statement timeout"
  }
};

describe("getErrorMessage — 오류 envelope 정규화", () => {
  it("v2 envelope는 한국어 라벨·코드·메시지·힌트를 한 줄로 보여 준다", () => {
    const error = new ApiError(504, JSON.stringify(V2_TIMEOUT_BODY));

    expect(getErrorMessage(error)).toBe(
      "DB 쿼리 시간 초과 [E0504]: database query timed out — 힌트: the query exceeded the DB statement timeout"
    );
  });

  it("v2 envelope의 field를 함께 표시한다", () => {
    const body = {
      status: "ERROR",
      query_id: "q-2",
      error: { code: "E0100", message: "invalid request data", field: "road_address" }
    };

    expect(getErrorMessage(new ApiError(400, JSON.stringify(body)))).toBe(
      "잘못된 입력 [E0100]: invalid request data (필드: road_address)"
    );
  });

  it("v1 비 VWorld·admin envelope(errorCode/errorMessage/hint)를 해석한다", () => {
    const body = {
      response: {
        status: "ERROR",
        errorCode: "E0500",
        errorMessage: "database connection failed",
        hint: "check the host/port in KTG_PG_DSN"
      }
    };

    expect(getErrorMessage(new ApiError(503, JSON.stringify(body)))).toBe(
      "DB 오류 [E0500]: database connection failed — 힌트: check the host/port in KTG_PG_DSN"
    );
  });

  it("v1 VWorld 호환 envelope(error.code/text)를 해석한다", () => {
    const body = {
      response: {
        service: { name: "address", version: "2.0", operation: "getCoord" },
        status: "ERROR",
        error: { level: 3, code: "SYSTEM_ERROR", text: "database query timed out" }
      }
    };

    expect(getErrorMessage(new ApiError(504, JSON.stringify(body)))).toBe(
      "시스템 오류 [SYSTEM_ERROR]: database query timed out"
    );
  });

  it("알 수 없는 코드는 일반 라벨로 표시한다", () => {
    const body = { status: "ERROR", query_id: "q", error: { code: "E9999", message: "boom" } };

    expect(getErrorMessage(new ApiError(500, JSON.stringify(body)))).toBe("API 오류 [E9999]: boom");
  });

  it("기존 detail·BFF error 문자열·비 JSON 본문 동작은 유지한다", () => {
    expect(getErrorMessage(new ApiError(502, JSON.stringify({ detail: "epost 서버 응답 없음" })))).toBe(
      "epost 서버 응답 없음"
    );
    expect(getErrorMessage(new ApiError(401, JSON.stringify({ error: "AUTH_REQUIRED" })))).toBe(
      "AUTH_REQUIRED"
    );
    expect(getErrorMessage(new ApiError(403, "Forbidden"))).toBe("Forbidden");
    expect(parseApiErrorEnvelope({ detail: "x" })).toBeNull();
    expect(parseApiErrorEnvelope({ response: { status: "OK" } })).toBeNull();
  });
});

describe("apiErrorResult / resultErrorMessage", () => {
  it("요약과 함께 HTTP status와 원본 envelope를 남긴다", () => {
    const result = apiErrorResult(new ApiError(504, JSON.stringify(V2_TIMEOUT_BODY)));

    expect(result.status).toBe(504);
    expect(result.response).toEqual(V2_TIMEOUT_BODY);
    expect(resultErrorMessage(result)).toContain("DB 쿼리 시간 초과 [E0504]");
  });

  it("일반 Error와 성공 응답을 구분한다", () => {
    expect(apiErrorResult(new Error("network down"))).toEqual({ error: "network down" });
    expect(resultErrorMessage({ status: "OK", candidates: [] })).toBeNull();
    expect(resultErrorMessage(null)).toBeNull();
  });
});
