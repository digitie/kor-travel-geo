/**
 * Shared cap for live SSE (`EventSource`) subscriptions rendered per table/list row.
 *
 * An `EventSource` pins one of the browser's **6 concurrent HTTP/1.1 connections per
 * origin** for its entire lifetime (prod serves the UI via `next start`, which is
 * HTTP/1.1 — see `kor-travel-geo-ui/Dockerfile`). Subscribing one stream per row therefore
 * starves every other same-origin request — navigation, react-query, even logout — as soon
 * as enough rows are live. Issue #512 hit exactly that on `/admin/source-files` (9 resumable
 * sessions → rail navigation hung ~5 min while curl answered in 0.79 s), and the identical
 * shape existed on `/admin/backups`, where one stream per non-terminal job could reach the
 * jobs query's limit of 50.
 *
 * Rows that do not get a slot are not left stale: their list query polls while any row is
 * still active, so they keep a coarse (non-live) status.
 */

/**
 * Concurrent live streams allowed per list. Two routes never mount their lists at once
 * (Radix unmounts inactive tabs; the panels live on different routes), so this is also the
 * effective page-wide ceiling — leaving at least 4 connections for everything else.
 */
export const MAX_LIVE_SSE_STREAMS = 2;

export type LiveStreamCandidate<T> = {
  /** Stable identity of the row (also the stream key). */
  id: (item: T) => string;
  /** Recency of the row; higher wins a slot. Invalid/absent → treated as oldest. */
  activity: (item: T) => string | null | undefined;
  /**
   * Rows that cannot currently produce events (e.g. a `failed_*` upload session that stays
   * resumable for retry). They stay eligible but sort last, so they never squat a slot while
   * an actually-progressing row goes without.
   */
  deprioritize?: (item: T) => boolean;
};

/**
 * Choose which rows get a live stream: the `max` most recently active, progressing rows.
 *
 * The order is deterministic — activity desc, then `id` — so the selection does not flap
 * between renders. An unstable selection would tear down and reopen `EventSource`s, which is
 * the very churn the cap exists to prevent.
 */
export function selectLiveStreamIds<T>(
  items: readonly T[],
  select: LiveStreamCandidate<T>,
  max: number = MAX_LIVE_SSE_STREAMS
): Set<string> {
  if (max <= 0) {
    return new Set();
  }
  const activityMs = (item: T): number => {
    const stamp = select.activity(item);
    const parsed = stamp ? Date.parse(stamp) : Number.NaN;
    return Number.isNaN(parsed) ? 0 : parsed;
  };
  const rank = (item: T): number => (select.deprioritize?.(item) ? 1 : 0);
  return new Set(
    [...items]
      .sort((a, b) => {
        const byRank = rank(a) - rank(b);
        if (byRank !== 0) {
          return byRank;
        }
        const byActivity = activityMs(b) - activityMs(a);
        return byActivity !== 0 ? byActivity : select.id(a).localeCompare(select.id(b));
      })
      .slice(0, max)
      .map(select.id)
  );
}
