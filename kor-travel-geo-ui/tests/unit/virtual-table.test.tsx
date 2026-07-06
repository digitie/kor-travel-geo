import { fireEvent, render, screen } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";

// jsdom has no layout, so give scroll elements a measurable height for the virtualizer.
describe("VirtualTable (T-254, TanStack Table + Virtual)", () => {
  let origHeight: PropertyDescriptor | undefined;
  let origRect: typeof Element.prototype.getBoundingClientRect;

  beforeAll(() => {
    origHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      value: 400
    });
    origRect = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function () {
      return {
        width: 800,
        height: 400,
        top: 0,
        left: 0,
        right: 800,
        bottom: 400,
        x: 0,
        y: 0,
        toJSON: () => ({})
      } as DOMRect;
    };
  });
  afterAll(() => {
    if (origHeight) Object.defineProperty(HTMLElement.prototype, "offsetHeight", origHeight);
    Element.prototype.getBoundingClientRect = origRect;
  });

  const data = [
    { id: "a", name: "alpha", size: 30 },
    { id: "b", name: "bravo", size: 10 }
  ];
  const columns: VirtualColumn<(typeof data)[number]>[] = [
    { key: "name", header: "name", sortValue: (r) => r.name, cell: (r) => r.name },
    { key: "size", header: "size", sortValue: (r) => r.size, cell: (r) => String(r.size) }
  ];

  it("renders rows and reports the visible/total count", () => {
    render(
      <VirtualTable
        columns={columns}
        getSearchText={(r) => r.name}
        rowKey={(r) => r.id}
        rows={data}
      />
    );
    expect(screen.getByText("2 / 2")).toBeTruthy();
    expect(screen.getByText("alpha")).toBeTruthy();
    expect(screen.getByText("bravo")).toBeTruthy();
  });

  it("filters by the search box (TanStack global filter)", () => {
    render(
      <VirtualTable
        columns={columns}
        getSearchText={(r) => r.name}
        rowKey={(r) => r.id}
        rows={data}
      />
    );
    fireEvent.change(screen.getByLabelText("목록 검색"), { target: { value: "alp" } });
    expect(screen.getByText("1 / 2")).toBeTruthy();
    expect(screen.queryByText("bravo")).toBeNull();
  });

  it("sorts ascending on the first header click (TanStack sorting)", () => {
    render(<VirtualTable columns={columns} rowKey={(r) => r.id} rows={data} />);
    fireEvent.click(screen.getByRole("button", { name: /^size/ }));
    expect(screen.getByRole("button", { name: /size ▲/ })).toBeTruthy();
  });

  it("renders virtualized grid markup with ARIA table roles (no <table> element)", () => {
    const { container } = render(
      <VirtualTable columns={columns} rowKey={(r) => r.id} rows={data} />
    );
    // 실제 <table> 요소는 없지만(가상화 div 그리드) 보조기기에는 table로 노출된다.
    expect(container.querySelector("table")).toBeNull();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("columnheader").length).toBe(2);
    expect(screen.getAllByRole("row").length).toBe(3); // 헤더 행 + 데이터 2행
    expect(screen.getAllByRole("cell").length).toBe(4);
    expect(container.querySelector(".vtable-grid")).toBeTruthy();
    expect(container.querySelectorAll(".vtable-th").length).toBe(2);
    expect(container.querySelectorAll(".vtable-row").length).toBe(2);
  });
});

describe("VirtualTable as='table' semantic mode (T-270)", () => {
  const data = [
    { id: "a", name: "alpha", size: 30 },
    { id: "b", name: "bravo", size: 10 }
  ];
  const columns: VirtualColumn<(typeof data)[number]>[] = [
    { key: "name", header: "name", sortValue: (r) => r.name, cell: (r) => r.name },
    { key: "size", header: "size", sortValue: (r) => r.size, cell: (r) => String(r.size), align: "right" }
  ];

  it("renders a real semantic <table> with caption, column headers, rows and cells", () => {
    render(
      <VirtualTable as="table" caption="목록 캡션" columns={columns} rowKey={(r) => r.id} rows={data} />
    );
    const table = screen.getByRole("table");
    expect(table.tagName).toBe("TABLE");
    expect(screen.getByText("목록 캡션").tagName).toBe("CAPTION");
    expect(screen.getAllByRole("columnheader").length).toBe(2);
    // header row + 2 data rows
    expect(screen.getAllByRole("row").length).toBe(3);
    expect(screen.getByRole("cell", { name: "alpha" })).toBeTruthy();
    // <th scope="col">
    expect(table.querySelectorAll("th[scope='col']").length).toBe(2);
  });

  it("sorts via the header button and sets aria-sort in table mode", () => {
    render(<VirtualTable as="table" columns={columns} rowKey={(r) => r.id} rows={data} />);
    fireEvent.click(screen.getByRole("button", { name: /^size/ }));
    const header = screen.getByRole("columnheader", { name: /size/ });
    expect(header.getAttribute("aria-sort")).toBe("ascending");
  });

  it("renders emptyHint in a spanning cell when there are no rows", () => {
    render(
      <VirtualTable as="table" columns={columns} emptyHint="없음" rowKey={(r) => r.id} rows={[]} />
    );
    const empty = screen.getByText("없음");
    expect(empty.getAttribute("colspan")).toBe("2");
  });

  it("supports custom header cells (e.g. select-all) and per-row className + row click", () => {
    const clicked: string[] = [];
    const selectColumn: VirtualColumn<(typeof data)[number]> = {
      key: "select",
      header: "",
      headerCell: <input aria-label="전체 선택" type="checkbox" />,
      cell: (r) => <input aria-label={`${r.name} 선택`} type="checkbox" />
    };
    const { container } = render(
      <VirtualTable
        as="table"
        columns={[selectColumn, ...columns]}
        getRowClassName={(r) => (r.id === "a" ? "active-row" : undefined)}
        onRowClick={(r) => clicked.push(r.id)}
        rowKey={(r) => r.id}
        rows={data}
      />
    );
    expect(screen.getByLabelText("전체 선택")).toBeTruthy();
    expect(screen.getByLabelText("alpha 선택")).toBeTruthy();
    expect(container.querySelectorAll("tr.active-row").length).toBe(1);
    fireEvent.click(screen.getByRole("cell", { name: "bravo" }));
    expect(clicked).toContain("b");
  });

  it("applies column alignment to header and body cells", () => {
    const { container } = render(
      <VirtualTable as="table" columns={columns} rowKey={(r) => r.id} rows={data} />
    );
    const rightCells = Array.from(container.querySelectorAll("td")).filter(
      (td) => (td as HTMLElement).style.textAlign === "right"
    );
    // size column (align: right) → 2 body cells
    expect(rightCells.length).toBe(2);
  });

  it("suppresses the thead when hideHeader is set (headerless key/value tables)", () => {
    const { container } = render(
      <VirtualTable as="table" columns={columns} hideHeader rowKey={(r) => r.id} rows={data} />
    );
    expect(container.querySelector("thead")).toBeNull();
    expect(screen.queryAllByRole("columnheader").length).toBe(0);
    // body rows still render
    expect(screen.getByRole("cell", { name: "alpha" })).toBeTruthy();
  });

  it("renders rowHeader columns as <th scope='row'> in the body", () => {
    const kvColumns: VirtualColumn<(typeof data)[number]>[] = [
      { key: "name", header: "name", cell: (r) => r.name, rowHeader: true },
      { key: "size", header: "size", cell: (r) => String(r.size) }
    ];
    const { container } = render(
      <VirtualTable as="table" columns={kvColumns} hideHeader rowKey={(r) => r.id} rows={data} />
    );
    const rowHeaders = container.querySelectorAll("tbody th[scope='row']");
    expect(rowHeaders.length).toBe(2);
    expect(rowHeaders[0]?.textContent).toBe("alpha");
    // the non-rowHeader column is still a <td>
    expect(screen.getByRole("cell", { name: "30" })).toBeTruthy();
  });
});
