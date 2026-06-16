import { describe, expect, it } from "vitest";
import { diffMatchSets } from "@/lib/match-set-diff";
import type { SourceMatchSet, SourceMatchSetDetail, SourceMatchSetItem } from "@/lib/source-files";

function item(over: Partial<SourceMatchSetItem> & { category: string }): SourceMatchSetItem {
  return {
    source_match_set_item_id: `it-${over.category}`,
    source_match_set_id: "ms",
    role: "build_required",
    omitted: false,
    required: true,
    validation_enabled: true,
    effective_yyyymm: "202603",
    source_file_group_id: "grp_a",
    ...over
  } as SourceMatchSetItem;
}

function detail(over: Partial<SourceMatchSet>, items: SourceMatchSetItem[]): SourceMatchSetDetail {
  return {
    match_set: {
      source_match_set_id: "ms",
      name: "set",
      profile: "serving_recommended",
      state: "active",
      integrity_alert: false,
      mixed_yyyymm: false,
      source_set_hash: "hashA",
      created_at: "2026-06-01T00:00:00Z",
      updated_at: "2026-06-01T00:00:00Z",
      ...over
    } as SourceMatchSet,
    items
  };
}

describe("diffMatchSets (T-226)", () => {
  it("classifies added/removed/changed/same with counts", () => {
    const a = detail({ source_set_hash: "hashA" }, [
      item({ category: "roadname_hangul_full" }), // same in both
      item({ category: "locsum_full", effective_yyyymm: "202604" }), // changed (yyyymm)
      item({ category: "navi_full" }) // removed (only in A)
    ]);
    const b = detail({ source_set_hash: "hashB" }, [
      item({ category: "roadname_hangul_full" }),
      item({ category: "locsum_full", effective_yyyymm: "202605" }),
      item({ category: "epost_pobox_full" }) // added (only in B)
    ]);

    const diff = diffMatchSets(a, b);
    expect(diff.counts).toEqual({ added: 1, removed: 1, changed: 1, same: 1 });

    const byCat = Object.fromEntries(diff.items.map((i) => [i.category, i.status]));
    expect(byCat.roadname_hangul_full).toBe("same");
    expect(byCat.locsum_full).toBe("changed");
    expect(byCat.navi_full).toBe("removed");
    expect(byCat.epost_pobox_full).toBe("added");

    const locsum = diff.items.find((i) => i.category === "locsum_full");
    expect(locsum?.changedFields).toEqual(["effective_yyyymm"]);
  });

  it("detects role/group/omitted field changes", () => {
    const a = detail({}, [
      item({ category: "locsum_full", role: "build_required", omitted: false, source_file_group_id: "g1" })
    ]);
    const b = detail({}, [
      item({ category: "locsum_full", role: "enrichment_candidate", omitted: true, source_file_group_id: "g2" })
    ]);
    const diff = diffMatchSets(a, b);
    const row = diff.items[0];
    expect(row.status).toBe("changed");
    expect(new Set(row.changedFields)).toEqual(
      new Set(["role", "omitted", "source_file_group_id"])
    );
  });

  it("computes set-level meta deltas", () => {
    const a = detail({ profile: "serving_recommended", source_set_hash: "h1", mixed_yyyymm: false, state: "active" }, []);
    const b = detail({ profile: "lean", source_set_hash: "h2", mixed_yyyymm: true, state: "retired" }, []);
    const diff = diffMatchSets(a, b);
    const changed = Object.fromEntries(diff.setMeta.map((m) => [m.field, m.changed]));
    expect(changed.profile).toBe(true);
    expect(changed.source_set_hash).toBe(true);
    expect(changed.mixed_yyyymm).toBe(true);
    expect(changed.state).toBe(true);
    const hashRow = diff.setMeta.find((m) => m.field === "source_set_hash");
    expect(hashRow).toMatchObject({ a: "h1", b: "h2" });
  });
});
