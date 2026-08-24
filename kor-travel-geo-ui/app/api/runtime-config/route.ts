import { NextResponse } from "next/server";
import { recordUiRequest } from "@/lib/metrics";
import { resolveDagsterPublicUrl, resolveVWorldApiKey } from "@/lib/runtime-config";
import { sessionIsValidInNode } from "@/lib/session-guard";

export const dynamic = "force-dynamic";

export async function GET() {
  const startedAt = performance.now();
  let statusCode = 500;
  try {
    // This returns the VWorld API key, so it must not rely on the Edge middleware alone:
    // middleware cannot see revoked sessions, and a cookie copied before logout used to
    // still get the key back (issue #513). Re-validate in Node, where revocation lives.
    if (!(await sessionIsValidInNode())) {
      const denied = NextResponse.json(
        { error: "AUTH_REQUIRED" },
        { status: 401, headers: { "cache-control": "no-store" } }
      );
      statusCode = denied.status;
      return denied;
    }
    const response = NextResponse.json(
      {
        vworldApiKey: resolveVWorldApiKey(),
        dagsterUrl: resolveDagsterPublicUrl()
      },
      {
        headers: {
          "cache-control": "no-store"
        }
      }
    );
    statusCode = response.status;
    return response;
  } finally {
    recordUiRequest({
      method: "GET",
      route: "/api/runtime-config",
      statusCode,
      elapsedSeconds: (performance.now() - startedAt) / 1000
    });
  }
}
