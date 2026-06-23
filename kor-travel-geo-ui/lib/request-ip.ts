type HeaderReader = { get(name: string): string | null };
type IpRequestLike = { headers: HeaderReader };
type Env = Record<string, string | undefined>;

const TRUSTED_PROXY_HOPS_ENV = "KTG_UI_TRUSTED_PROXY_HOPS";
const MAX_IP_LENGTH = 128;

/** Number of trusted reverse proxies in front of the UI (0 = reachable directly, default). */
export function trustedProxyHops(env: Env = process.env): number {
  const raw = Number((env[TRUSTED_PROXY_HOPS_ENV] ?? "").trim());
  return Number.isInteger(raw) && raw >= 0 ? raw : 0;
}

/**
 * Best-effort genuine client IP, hardened against `X-Forwarded-For` spoofing.
 *
 * `X-Forwarded-For` is only trusted when the deployment declares how many reverse proxies sit in
 * front of the UI via `KTG_UI_TRUSTED_PROXY_HOPS`. With N>0 trusted proxies that each APPEND their
 * immediate peer to XFF, the genuine client IP is the Nth entry from the right of the chain
 * (`chain[length - N]`); a client cannot forge it by prepending extra entries. Returns `null` when
 * there is no trustworthy IP (0 trusted hops, or fewer entries than declared hops) so callers do
 * not act on a client-controlled value.
 */
export function trustedClientIp(request: IpRequestLike, env: Env = process.env): string | null {
  const hops = trustedProxyHops(env);
  if (hops <= 0) {
    return null;
  }
  const chain = (request.headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
  const index = chain.length - hops;
  if (index < 0 || index >= chain.length) {
    return null;
  }
  return chain[index].slice(0, MAX_IP_LENGTH);
}

/**
 * Bucket key for rate-limiting. Uses the trusted client IP when available; otherwise a single
 * shared `"untrusted"` bucket, so an attacker cannot dodge the brute-force limit by rotating a
 * forged `X-Forwarded-For` header on each request.
 */
export function clientIpForThrottle(request: IpRequestLike, env: Env = process.env): string {
  return trustedClientIp(request, env) ?? "untrusted";
}
