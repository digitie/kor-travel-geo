import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VirtualTable, type VirtualColumn } from "@/components/ui/VirtualTable";

/**
 * Issue #514 structural guard for the table scroll region.
 *
 * jsdom does not apply `globals.css`, so the *visual* assertions live in the Playwright
 * viewport spec. What this file pins is the markup contract the CSS depends on, and the
 * accessibility properties a scrollable region must have:
 *
 *  - the scroller wraps ONLY the table (not the toolbar — otherwise the search box stretches
 *    to the table's width inside the scroller),
 *  - it is keyboard focusable with an accessible name, because Chromium refuses to auto-focus
 *    a scroll container that has focusable descendants and every sortable header is a button
 *    (WCAG 2.1.1),
 *  - the table keeps its native semantics (no `display: block` re-wrapping in the markup).
 */

type Row = { id: string; name: string };

const ROWS: Row[] = [
  { id: "a", name: "행 A" },
  { id: "b", name: "행 B" }
];

const COLUMNS: VirtualColumn<Row>[] = [
  { key: "id", header: "ID", cell: (row) => row.id, sortValue: (row) => row.id },
  { key: "name", header: "이름", cell: (row) => row.name }
];

function renderTable(extra?: Partial<Parameters<typeof VirtualTable<Row>>[0]>) {
  return render(
    <VirtualTable
      as="table"
      caption="테스트 표"
      columns={COLUMNS}
      rowKey={(row) => row.id}
      rows={ROWS}
      {...extra}
    />
  );
}

describe("VirtualTable 가로 스크롤 영역 (#514)", () => {
  it("표를 감싸는 스크롤 영역이 키보드 포커스 가능하고 접근 가능한 이름을 가진다", () => {
    const { container } = renderTable();
    const scroll = container.querySelector(".vtable-scroll");
    expect(scroll, "스크롤 래퍼가 있어야 한다").not.toBeNull();
    // A scrollable region must be reachable by keyboard, and a focusable region needs a name.
    expect(scroll).toHaveAttribute("tabindex", "0");
    expect(scroll).toHaveAttribute("role", "region");
    expect(scroll?.getAttribute("aria-label")).toBe("테스트 표");
  });

  it("caption이 없어도 스크롤 영역에 이름이 있다", () => {
    const { container } = render(
      <VirtualTable as="table" columns={COLUMNS} rowKey={(row) => row.id} rows={ROWS} />
    );
    const scroll = container.querySelector(".vtable-scroll");
    expect(scroll?.getAttribute("aria-label")).toBeTruthy();
  });

  it("스크롤 영역은 표만 감싸고 툴바는 밖에 둔다", () => {
    // If the toolbar were inside, it would stretch to the table's scroll width.
    const { container } = renderTable({ getSearchText: (row) => row.name });
    // Guard the guard: the toolbar must actually be rendered for this assertion to mean anything.
    expect(container.querySelector(".vtable-toolbar"), "툴바가 렌더되어야 한다").not.toBeNull();
    const scroll = container.querySelector(".vtable-scroll");
    expect(scroll?.querySelector("table"), "표는 스크롤 영역 안에").not.toBeNull();
    expect(scroll?.querySelector(".vtable-toolbar"), "툴바는 스크롤 영역 밖에").toBeNull();
  });

  it("표의 네이티브 시맨틱이 유지된다", () => {
    renderTable();
    // Native <table> semantics — the fix must not re-wrap the table into a block box.
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(COLUMNS.length);
    expect(screen.getAllByRole("row").length).toBeGreaterThan(ROWS.length - 1);
  });
});
