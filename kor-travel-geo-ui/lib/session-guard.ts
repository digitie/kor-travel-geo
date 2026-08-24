import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE_NAME, sanitizeLocalPath, verifySessionCookieValueNow } from "@/lib/auth";
import { PATHNAME_HEADER } from "@/lib/session-headers";

/**
 * Authoritative, Node-runtime session check for server components and route handlers.
 *
 Defence in depth behind `proxy.ts`, which is the authoritative gate (it runs in Node and sees
 * the revocation list, so it covers document, RSC and client-side-navigation requests alike).
 * This helper exists for anything that wants to fail closed on its own rather than trust the
 * pre-render gate.
 *
 * Do NOT rely on a layout `redirect()` as an authorization boundary: for an RSC request Next
 * streams a 200 carrying the redirect digest *and* the rendered payload, and on client-side
 * navigation Next skips already-matching segments so the layout never runs (issue #513).
 *
 * The revocation list is pinned to `globalThis` in `lib/auth.ts` — the bundler emits that
 * module once per layer, so without pinning the pages would read a different (always empty)
 * map than the logout route and every revoked session would silently pass.
 *
 * Residual limitation: revocation is in-process, so a UI restart clears it and sessions valid
 * until `SESSION_TTL_SECONDS` become replayable again. (The UI runs as a single container —
 * `kor-travel-geo-ui/Dockerfile` — so cross-replica sharing is not currently a concern.)
 * Durable logout needs shared state; the backend already receives an `admin_auth.logout` audit
 * event, so the natural follow-up is to reject sessions issued before the newest logout event,
 * failing closed on backend error. Tracked as the #513 follow-up.
 */
export async function sessionIsValidInNode(): Promise<boolean> {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const session = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  return verifySessionCookieValueNow(session, process.env, headerStore);
}

/**
 * Redirect to `/login` unless the caller holds a still-valid (non-revoked) session.
 *
 * Preserves where the operator was heading in `?next=` (the path is handed down by `proxy.ts`)
 * so a revoked session does not silently lose its destination on re-login.
 */
export async function requireSession(): Promise<void> {
  if (await sessionIsValidInNode()) {
    return;
  }
  const headerStore = await headers();
  // Supplied by the middleware; absent for paths its matcher skips (e.g. `*.js`), in which
  // case we simply send the operator to a bare /login.
  const requested = headerStore.get(PATHNAME_HEADER);
  const target = requested ? sanitizeLocalPath(requested, "") : "";
  redirect(target ? `/login?next=${encodeURIComponent(target)}` : "/login");
}
