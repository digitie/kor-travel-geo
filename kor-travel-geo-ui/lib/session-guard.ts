import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE_NAME, verifySessionCookieValueNow } from "@/lib/auth";

/**
 * Authoritative, Node-runtime session check for server components and route handlers.
 *
 * `middleware.ts` runs on the **Edge runtime** and is only a fast-path gate: it rejects
 * requests with no/expired/forged cookie, but it cannot see `revokeSessionCookieValue`'s
 * revocation list, which lives in the Node module instance the logout route writes to. A
 * cookie copied before logout therefore still satisfies the middleware (issue #513).
 *
 * Anything that renders the app or returns data/secrets must therefore re-validate **here**,
 * in Node, rather than trusting the middleware alone.
 *
 * Residual limitation (documented, not fixed by this helper): the revocation list is
 * in-process, so it is lost on UI restart and is not shared across replicas. Sessions still
 * expire on their own (`SESSION_TTL_SECONDS`), and every data path goes through
 * `/api/proxy/*`, which re-validates in Node on each call. Making logout durable across
 * restarts needs a shared store — tracked as the follow-up on #513.
 */
export async function sessionIsValidInNode(): Promise<boolean> {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const session = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  return verifySessionCookieValueNow(session, process.env, headerStore);
}

/** Redirect to `/login` unless the caller holds a still-valid (non-revoked) session. */
export async function requireSession(): Promise<void> {
  if (!(await sessionIsValidInNode())) {
    redirect("/login");
  }
}
