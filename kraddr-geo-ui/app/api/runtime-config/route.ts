import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(
    {
      vworldApiKey: process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ""
    },
    {
      headers: {
        "cache-control": "no-store"
      }
    }
  );
}
