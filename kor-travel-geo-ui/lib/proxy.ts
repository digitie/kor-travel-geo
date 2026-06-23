import { KNOWN_ADMIN_ROLES, type AdminRole } from "@/lib/roles";

const ALLOWED_FORWARD_HEADERS = new Set(["accept", "content-type", "user-agent"]);
const KNOWN_ADMIN_ROLE_SET = new Set<string>(KNOWN_ADMIN_ROLES);

const LIVE_E2E_ADMIN_PROXY_ENV = "KTG_LIVE_E2E_ADMIN_PROXY";
const LIVE_E2E_ADMIN_ACTOR_ENV = "KTG_LIVE_E2E_ADMIN_ACTOR";
const LIVE_E2E_ADMIN_ROLES_ENV = "KTG_LIVE_E2E_ADMIN_ROLES";
const ADMIN_PROXY_SECRET_ENV = "KTG_ADMIN_PROXY_SECRET";

export type ProxyRequestInit = RequestInit & { duplex?: "half" };
type Env = Record<string, string | undefined>;

export type LiveE2EAdminIdentity = {
  actor: string;
  roles: AdminRole[];
};

export function buildProxyTarget(
  pathSegments: string[],
  search: string,
  internalBase: string
): URL | null {
  const target = new URL(`/${pathSegments.join("/")}`, internalBase);
  target.search = search;
  return target.pathname.startsWith("/v1/") || target.pathname.startsWith("/v2/")
    ? target
    : null;
}

function isEnabled(value: string | undefined): boolean {
  return value === "1" || value?.toLowerCase() === "true";
}

function parseLiveE2EAdminRoles(raw: string | undefined): AdminRole[] {
  if (!raw) {
    return [];
  }
  const roles = raw
    .split(",")
    .map((role) => role.trim())
    .filter((role): role is AdminRole => KNOWN_ADMIN_ROLE_SET.has(role));
  return [...new Set(roles)];
}

export function liveE2EAdminIdentityFromEnv(
  env: Env = process.env
): LiveE2EAdminIdentity | null {
  if (!isEnabled(env[LIVE_E2E_ADMIN_PROXY_ENV])) {
    return null;
  }
  const actor = (env[LIVE_E2E_ADMIN_ACTOR_ENV] ?? "").trim();
  if (!actor) {
    return null;
  }
  const roles = parseLiveE2EAdminRoles(env[LIVE_E2E_ADMIN_ROLES_ENV]);
  if (roles.length === 0) {
    return null;
  }
  return { actor, roles };
}

export function forwardedProxyHeaders(
  source: Headers,
  env: Env = process.env,
  sessionIdentity: LiveE2EAdminIdentity | null = null
): Headers {
  const headers = new Headers();
  source.forEach((value, key) => {
    if (ALLOWED_FORWARD_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  const identity = sessionIdentity ?? liveE2EAdminIdentityFromEnv(env);
  if (identity !== null) {
    headers.set("X-KTG-Actor", identity.actor);
    headers.set("X-KTG-Roles", identity.roles.join(","));
    const proxySecret = env[ADMIN_PROXY_SECRET_ENV]?.trim();
    if (proxySecret) {
      headers.set("X-KTG-Admin-Proxy-Secret", proxySecret);
    }
  }
  return headers;
}

export function buildProxyRequestInit(
  method: string,
  headers: Headers,
  body: ReadableStream<Uint8Array> | null,
  signal?: AbortSignal
): ProxyRequestInit {
  const init: ProxyRequestInit = {
    method,
    headers,
    cache: "no-store",
    // Propagate the client's abort to the upstream fetch. Without this, a
    // cancelled/navigated-away request leaks the undici connection (the backend
    // keeps running and the response stream is never drained) — repeated leaks
    // exhaust the pool and later requests stall. (cf. kor-travel-concierge #111)
    signal
  };
  if (method !== "GET" && method !== "HEAD" && body !== null) {
    init.body = body;
    init.duplex = "half";
  }
  return init;
}
