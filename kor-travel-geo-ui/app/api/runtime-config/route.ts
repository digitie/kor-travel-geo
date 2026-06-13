import { NextResponse } from "next/server";
import { recordUiRequest } from "@/lib/metrics";
import { resolveVWorldApiKey } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export function GET() {
  const startedAt = performance.now();
  let statusCode = 500;
  try {
    const response = NextResponse.json(
      {
        vworldApiKey: resolveVWorldApiKey()
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
