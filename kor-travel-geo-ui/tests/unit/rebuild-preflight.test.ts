import { describe, expect, it } from "vitest";
import { summarizeRebuildPreflight } from "@/lib/rebuild-preflight";
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
      source_set_hash: "h",
      created_at: "2026-06-01T00:00:00Z",
      updated_at: "2026-06-01T00:00:00Z",
      ...over
    } as SourceMatchSet,
    items
  };
}

function severityOf(pf: ReturnType<typeof summarizeRebuildPreflight>, key: string) {
  return pf.items.find((i) => i.key === key)?.severity;
}

describe("summarizeRebuildPreflight (T-226)", () => {
  it("active set with all groups linked → ready, no blockers", () => {
    const pf = summarizeRebuildPreflight(
      detail({ state: "active", integrity_alert: false }, [
        item({ category: "roadname_hangul_full" }),
        item({ category: "locsum_full" })
      ])
    );
    expect(pf.ready).toBe(true);
    expect(pf.blockerCount).toBe(0);
    expect(severityOf(pf, "state")).toBe("ok");
    expect(severityOf(pf, "integrity")).toBe("ok");
    expect(severityOf(pf, "groups")).toBe("ok");
    expect(pf.affectedCategories).toEqual(["roadname_hangul_full", "locsum_full"]);
  });

  it("integrity_alert → blocker", () => {
    const pf = summarizeRebuildPreflight(detail({ integrity_alert: true }, [item({ category: "locsum_full" })]));
    expect(severityOf(pf, "integrity")).toBe("blocker");
    expect(pf.ready).toBe(false);
  });

  it("required item missing group → blocker; optional missing → warn", () => {
    const requiredMissing = summarizeRebuildPreflight(
      detail({}, [item({ category: "locsum_full", required: true, source_file_group_id: null })])
    );
    expect(severityOf(requiredMissing, "groups")).toBe("blocker");
    expect(requiredMissing.ready).toBe(false);

    const optionalMissing = summarizeRebuildPreflight(
      detail({}, [
        item({ category: "roadname_hangul_full" }),
        item({ category: "epost_pobox_full", required: false, source_file_group_id: null })
      ])
    );
    expect(severityOf(optionalMissing, "groups")).toBe("warn");
    expect(optionalMissing.ready).toBe(true);
  });

  it("non-active state → warn; all-omitted → affected blocker", () => {
    const retired = summarizeRebuildPreflight(detail({ state: "retired" }, [item({ category: "locsum_full" })]));
    expect(severityOf(retired, "state")).toBe("warn");

    const allOmitted = summarizeRebuildPreflight(
      detail({}, [item({ category: "locsum_full", omitted: true })])
    );
    expect(severityOf(allOmitted, "affected")).toBe("blocker");
    expect(allOmitted.affectedCategories).toEqual([]);
  });
});
