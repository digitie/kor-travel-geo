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
});
