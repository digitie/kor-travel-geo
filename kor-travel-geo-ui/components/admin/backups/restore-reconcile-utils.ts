import type { RestoreReconcileResult } from "@/lib/api";

/**
 * Extract the T-233 ``row_count_verification`` reconcile block from a ``db_restore_log``
 * artifact manifest. Returns null for legacy restore logs that predate T-233.
 */
export function reconcileFromManifest(
  manifest: Record<string, unknown> | undefined
): RestoreReconcileResult | null {
  const block = manifest?.["row_count_verification"];
  if (!block || typeof block !== "object") return null;
  return block as RestoreReconcileResult;
}
