import { describe, expect, it } from "vitest";
import { clientIpForThrottle, trustedClientIp, trustedProxyHops } from "@/lib/request-ip";

function req(xff?: string) {
  const headers = new Map<string, string>();
  if (xff !== undefined) headers.set("x-forwarded-for", xff);
  return { headers: { get: (name: string) => headers.get(name.toLowerCase()) ?? null } };
}

describe("request-ip trusted client IP", () => {
  it("0 trusted hops (default): X-Forwarded-For is never trusted", () => {
    expect(trustedProxyHops({})).toBe(0);
    expect(trustedClientIp(req("203.0.113.9"), {})).toBeNull();
    // The throttle bucket collapses to one shared key so a rotating forged XFF cannot dodge it.
    expect(clientIpForThrottle(req("203.0.113.9"), {})).toBe("untrusted");
    expect(clientIpForThrottle(req("9.9.9.9"), {})).toBe("untrusted");
  });

  it("1 trusted hop: reads the right-most (proxy-appended) entry, ignoring client-prepended forgery", () => {
    const env = { KTG_UI_TRUSTED_PROXY_HOPS: "1" };
    expect(trustedClientIp(req("203.0.113.9"), env)).toBe("203.0.113.9");
    // Client prepends a fake; the trusted proxy appends the real peer on the right.
    expect(trustedClientIp(req("1.2.3.4, 203.0.113.9"), env)).toBe("203.0.113.9");
    expect(clientIpForThrottle(req("1.2.3.4, 203.0.113.9"), env)).toBe("203.0.113.9");
  });

  it("N trusted hops: client IP is the Nth-from-right entry", () => {
    const env = { KTG_UI_TRUSTED_PROXY_HOPS: "2" };
    // chain = [forged, client, innerProxy]; with 2 trusted proxies the client is index len-2.
    expect(trustedClientIp(req("9.9.9.9, 203.0.113.9, 10.0.0.1"), env)).toBe("203.0.113.9");
  });

  it("fewer entries than declared hops, or missing header → null/untrusted (no forged fallback)", () => {
    const env = { KTG_UI_TRUSTED_PROXY_HOPS: "2" };
    expect(trustedClientIp(req("203.0.113.9"), env)).toBeNull();
    expect(trustedClientIp(req(), env)).toBeNull();
    expect(clientIpForThrottle(req(), env)).toBe("untrusted");
  });

  it("invalid/negative hop counts fall back to 0 (untrusted)", () => {
    expect(trustedProxyHops({ KTG_UI_TRUSTED_PROXY_HOPS: "-1" })).toBe(0);
    expect(trustedProxyHops({ KTG_UI_TRUSTED_PROXY_HOPS: "x" })).toBe(0);
    expect(trustedClientIp(req("203.0.113.9"), { KTG_UI_TRUSTED_PROXY_HOPS: "x" })).toBeNull();
  });
});
