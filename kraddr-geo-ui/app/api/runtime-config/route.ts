import { NextResponse } from "next/server";
import { resolveVWorldApiKey } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(
    {
      vworldApiKey: resolveVWorldApiKey()
    },
    {
      headers: {
        "cache-control": "no-store"
      }
    }
  );
}
