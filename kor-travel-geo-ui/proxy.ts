// Pre-render request gate (Next 16 `proxy` convention, formerly `middleware`).
//
// Runs in the **Node runtime**, so unlike the old Edge middleware it sees the revocation list
// in `lib/auth.ts` (pinned to `globalThis`). That makes this the authoritative gate for every
// request shape — document, RSC, and client-side navigation alike — which a layout `redirect()`
// cannot be: for an RSC request Next streams a 200 carrying the redirect digest *and* the
// rendered payload, and on client-side navigation Next skips already-matching segments so the
// layout never executes at all (issue #513).
import { NextRequest, NextResponse } from "next/server";
import { requestHasValidSession, sanitizeLocalPath } from "@/lib/auth";
import { PATHNAME_HEADER } from "@/lib/session-headers";

const PUBLIC_PATH_PREFIXES = ["/api/auth/", "/_next/", "/favicon.ico"];

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const validSession = await requestHasValidSession(request);
  if (validSession) {
    if (pathname === "/login") {
      const redirectPath = sanitizeLocalPath(request.nextUrl.searchParams.get("next"));
      return NextResponse.redirect(new URL(redirectPath, request.url));
    }
    // Pass the requested path down to the Node-side guard (`lib/session-guard.ts`), which
    // re-checks revocation and needs somewhere to send the operator back to. `headers()` has
    // no reliable pathname in the App Router, so the middleware supplies it. A spoofed value
    // is harmless: it is only fed to `sanitizeLocalPath`, which rejects non-local targets.
    const forwarded = new Headers(request.headers);
    forwarded.set(PATHNAME_HEADER, `${pathname}${request.nextUrl.search}`);
    return NextResponse.next({ request: { headers: forwarded } });
  }

  if (pathname.startsWith("/api/")) {
    // no-store: an auth decision must never be cached by a proxy or the browser.
    return NextResponse.json(
      { error: "AUTH_REQUIRED" },
      { status: 401, headers: { "cache-control": "no-store" } }
    );
  }

  const nextPath = `${pathname}${request.nextUrl.search}`;
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", nextPath);
  return NextResponse.redirect(loginUrl);
}

function isPublicPath(pathname: string): boolean {
  return (
    pathname === "/login" ||
    PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|.*\\.(?:ico|png|jpg|jpeg|svg|webp|gif|css|js|map)$).*)"
  ]
};
