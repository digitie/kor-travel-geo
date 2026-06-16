import type { SourceMatchSetDetail, SourceMatchSetItem } from "@/lib/source-files";

/**
 * T-226: pure source-match-set comparison helpers. Compares two `SourceMatchSetDetail`s
 * (fetched via the existing per-id endpoint) to surface "현재 구성 diff" / "match set 비교":
 * which categories were added/removed/changed between a base set (A) and a target set (B),
 * plus set-level field deltas. No backend changes needed — diff is computed client-side.
 */

export type ItemDiffStatus = "added" | "removed" | "changed" | "same";

/** A diff row keyed by category (one item per category per set is assumed; first wins on dupes). */
export type MatchSetItemDiff = {
  category: string;
  status: ItemDiffStatus;
  /** Item from the base set (A), or null if only in B (added). */
  a: SourceMatchSetItem | null;
  /** Item from the target set (B), or null if only in A (removed). */
  b: SourceMatchSetItem | null;
  /** Fields that differ when status === "changed". */
  changedFields: ItemField[];
};

export type MatchSetFieldDiff = {
  field: string;
  a: string | null;
  b: string | null;
  changed: boolean;
};

export type MatchSetDiff = {
  items: MatchSetItemDiff[];
  setMeta: MatchSetFieldDiff[];
  counts: { added: number; removed: number; changed: number; same: number };
};

type ItemField = "role" | "effective_yyyymm" | "omitted" | "source_file_group_id";

const ITEM_FIELDS: ItemField[] = ["role", "effective_yyyymm", "omitted", "source_file_group_id"];

function indexByCategory(items: SourceMatchSetItem[]): Map<string, SourceMatchSetItem> {
  const map = new Map<string, SourceMatchSetItem>();
  for (const item of items) {
    if (!map.has(item.category)) map.set(item.category, item);
  }
  return map;
}

function itemFieldValue(item: SourceMatchSetItem, field: ItemField): string | null {
  const value = item[field];
  if (value == null) return null;
  return typeof value === "boolean" ? String(value) : String(value);
}

function changedItemFields(a: SourceMatchSetItem, b: SourceMatchSetItem): ItemField[] {
  return ITEM_FIELDS.filter((field) => itemFieldValue(a, field) !== itemFieldValue(b, field));
}

function metaValue(value: unknown): string | null {
  if (value == null) return null;
  return typeof value === "boolean" ? String(value) : String(value);
}

/** Diff base set A against target set B (B is the "other"/comparison side). */
export function diffMatchSets(a: SourceMatchSetDetail, b: SourceMatchSetDetail): MatchSetDiff {
  const aItems = indexByCategory(a.items ?? []);
  const bItems = indexByCategory(b.items ?? []);
  const categories = [...new Set([...aItems.keys(), ...bItems.keys()])].sort();

  const items: MatchSetItemDiff[] = [];
  const counts = { added: 0, removed: 0, changed: 0, same: 0 };

  for (const category of categories) {
    const ai = aItems.get(category) ?? null;
    const bi = bItems.get(category) ?? null;
    let status: ItemDiffStatus;
    let changedFields: ItemField[] = [];
    if (ai && !bi) {
      status = "removed";
    } else if (!ai && bi) {
      status = "added";
    } else if (ai && bi) {
      changedFields = changedItemFields(ai, bi);
      status = changedFields.length > 0 ? "changed" : "same";
    } else {
      status = "same"; // unreachable (category came from one of the maps)
    }
    counts[status] += 1;
    items.push({ category, status, a: ai, b: bi, changedFields });
  }

  const setMeta: MatchSetFieldDiff[] = (
    [
      ["profile", a.match_set.profile, b.match_set.profile],
      ["state", a.match_set.state, b.match_set.state],
      ["source_set_hash", a.match_set.source_set_hash, b.match_set.source_set_hash],
      ["mixed_yyyymm", a.match_set.mixed_yyyymm, b.match_set.mixed_yyyymm]
    ] as const
  ).map(([field, av, bv]) => {
    const as = metaValue(av);
    const bs = metaValue(bv);
    return { field, a: as, b: bs, changed: as !== bs };
  });

  return { items, setMeta, counts };
}
