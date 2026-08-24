import { requireSession } from "@/lib/session-guard";

/** Server-side auth gate for `/debug/*` — see `app/admin/layout.tsx` (issue #513). */
export default async function DebugLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return <>{children}</>;
}
