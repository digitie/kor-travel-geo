import { requireSession } from "@/lib/session-guard";

/**
 * Server-side auth gate for every `/admin/*` page.
 *
 * The Edge middleware cannot see session revocations (issue #513), so a cookie copied before
 * logout would still render the admin shell. Re-validating in the Node runtime here closes
 * that. This makes the admin pages dynamic, which is correct for an auth-gated console.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return <>{children}</>;
}
