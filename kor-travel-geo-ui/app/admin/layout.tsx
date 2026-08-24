import { requireSession } from "@/lib/session-guard";

/**
 * Defence-in-depth auth check for `/admin/*`.
 *
 * The authoritative gate is `proxy.ts` (Node runtime, sees revocations). A layout `redirect()`
 * is NOT sufficient on its own — RSC responses still stream the rendered payload, and
 * client-side navigation skips already-matching segments so this never runs (issue #513).
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return <>{children}</>;
}
