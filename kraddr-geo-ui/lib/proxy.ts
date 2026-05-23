const ALLOWED_FORWARD_HEADERS = new Set(["accept", "content-type", "user-agent"]);

export type ProxyRequestInit = RequestInit & { duplex?: "half" };

export function buildProxyTarget(
  pathSegments: string[],
  search: string,
  internalBase: string
): URL | null {
  const target = new URL(`/${pathSegments.join("/")}`, internalBase);
  target.search = search;
  return target.pathname.startsWith("/v1/") ? target : null;
}

export function forwardedProxyHeaders(source: Headers): Headers {
  const headers = new Headers();
  source.forEach((value, key) => {
    if (ALLOWED_FORWARD_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  return headers;
}

export function buildProxyRequestInit(
  method: string,
  headers: Headers,
  body: ReadableStream<Uint8Array> | null
): ProxyRequestInit {
  const init: ProxyRequestInit = {
    method,
    headers,
    cache: "no-store"
  };
  if (method !== "GET" && method !== "HEAD" && body !== null) {
    init.body = body;
    init.duplex = "half";
  }
  return init;
}
