import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE_NAME, sanitizeLocalPath, verifySessionCookieValueNow } from "@/lib/auth";
import { PATHNAME_HEADER } from "@/lib/session-headers";

/**
 * Authoritative, Node-runtime session check for server components and route handlers.
 *
 * `middleware.ts` runs on the **Edge runtime** and is only a fast-path gate: it rejects
 * requests with no/expired/forged cookie, but it cannot see the revocation list that the Node
 * logout route writes. A cookie copied before logout therefore satisfies it (issue #513), so
 * anything that renders the app or returns data/secrets re-validates here, in Node.
 *
 * The revocation list itself is pinned to `globalThis` in `lib/auth.ts` — without that, the
 * bundler's per-layer module copies would give pages a different (always empty) map than the
 * logout route, and this guard would silently pass every revoked session.
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
 * Preserves where the operator was heading in `?next=`, matching the middleware's behaviour so
 * a revoked session does not silently lose its destination on re-login.
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
