import { formatAdminTitle } from "@kor-travel/ui/admin-shell";
import { describe, expect, it } from "vitest";
import { ADMIN_PAGES, DEBUG_PAGES, GEO_ADMIN_AREA, adminPageHeading, pageMetaForPath } from "@/lib/admin-pages";

describe("admin-pages 제목 정본", () => {
  it("adminPageHeading은 공통 formatAdminTitle과 같은 문자열이다", () => {
    for (const page of [...Object.values(ADMIN_PAGES), ...Object.values(DEBUG_PAGES)]) {
      expect(adminPageHeading(page.title)).toBe(formatAdminTitle(GEO_ADMIN_AREA, page.title));
    }
  });

  it("경로의 가장 긴 일치 페이지를 고른다", () => {
    expect(pageMetaForPath("/admin")?.title).toBe(ADMIN_PAGES.home.title);
    expect(pageMetaForPath("/admin/consistency/report-1")?.title).toBe(ADMIN_PAGES.consistency.title);
    expect(pageMetaForPath("/admin/load")?.title).toBe(ADMIN_PAGES.load.title);
    expect(pageMetaForPath("/debug/explain")).toEqual({
      title: DEBUG_PAGES.explain.title,
      description: DEBUG_PAGES.explain.description
    });
    expect(pageMetaForPath("/unknown")).toBeUndefined();
  });
});
