import type { NextRequest } from "next/server";

const INTERNAL_BASE = process.env.KTG_API_INTERNAL_URL ?? "http://localhost:12501";
const ADMIN_PROXY_SECRET_ENV = "KTG_ADMIN_PROXY_SECRET";
const AUTH_AUDIT_ACTOR = "ui-auth";
const AUTH_AUDIT_ROLES = "source_file_viewer";

type AuthAuditEvent = {
  attemptedUsername?: string | null;
  eventType: "login" | "logout";
  nextPath?: string | null;
  outcome: "succeeded" | "failed" | "denied";
  reason?: string | null;
};

export async function recordAuthAuditEvent(
  request: NextRequest,
  event: AuthAuditEvent
): Promise<void> {
  const headers = new Headers({
    "content-type": "application/json",
    "x-ktg-actor": AUTH_AUDIT_ACTOR,
    "x-ktg-roles": AUTH_AUDIT_ROLES
  });
  const proxySecret = process.env[ADMIN_PROXY_SECRET_ENV]?.trim();
  if (proxySecret) {
    headers.set("x-ktg-admin-proxy-secret", proxySecret);
  }
  try {
    const target = new URL("/v1/admin/auth-events", INTERNAL_BASE);
    await fetch(target, {
      method: "POST",
      headers,
      body: JSON.stringify({
        attempted_username: event.attemptedUsername?.trim() || null,
        client_ip: clientIpFromRequest(request),
        event_type: event.eventType,
        next_path: event.nextPath ?? null,
        outcome: event.outcome,
        reason: event.reason ?? null,
        user_agent: request.headers.get("user-agent")
      })
    });
  } catch {
    // Login must not depend on audit persistence availability.
  }
}

function clientIpFromRequest(request: NextRequest): string | null {
  return (
    firstForwardedValue(request.headers.get("x-forwarded-for")) ??
    firstForwardedValue(request.headers.get("x-real-ip"))
  );
}

function firstForwardedValue(value: string | null): string | null {
  return value?.split(",")[0]?.trim() || null;
}
