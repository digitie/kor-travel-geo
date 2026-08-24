import { requireSession } from "@/lib/session-guard";

/** Defence-in-depth auth check for `/debug/*` — see `app/admin/layout.tsx` (issue #513). */
export default async function DebugLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return <>{children}</>;
}
