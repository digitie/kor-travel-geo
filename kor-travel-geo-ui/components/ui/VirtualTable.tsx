"use client";

// TanStack Table/Virtual hooks return fresh functions by design; the plugin's memoization
// heuristic flags useReactTable()/useVirtualizer() as a false positive across this file.
/* eslint-disable react-hooks/incompatible-library */

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  type Row,
  type SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";

export type VirtualColumn<T> = {
  key: string;
  header: string;
  /** Custom header content (e.g. a select-all checkbox). Overrides `header`; not sortable. */
  headerCell?: ReactNode;
  cell: (row: T) => ReactNode;
  /** Provide to make the column sortable (click the header to toggle asc/desc). */
  sortValue?: (row: T) => string | number | null | undefined;
  /** Cell/header text alignment (default left). */
  align?: "left" | "right" | "center";
  /** Extra class on each body cell (table mode `<td>` / grid mode `.vtable-td`). */
  cellClassName?: string;
  /**
   * In `as="table"` mode, render this column's body cell as a row header
   * (`<th scope="row">`) instead of `<td>` — for transposed key/value tables
   * (e.g. field-by-field comparison). No effect in grid mode.
   */
  rowHeader?: boolean;
  /** CSS grid track for this column in grid mode (default ``1fr``). */
  width?: string;
};

type CommonProps<T> = {
  rows: T[];
  columns: VirtualColumn<T>[];
  rowKey: (row: T) => string;
  getSearchText?: (row: T) => string;
  searchPlaceholder?: string;
  emptyHint?: string;
  initialSortKey?: string | null;
  initialSortDir?: "asc" | "desc";
  /** Accessible caption (semantic `as="table"` mode renders a `<caption>`). */
  caption?: string;
  /** Per-row class (e.g. active/selected/changed highlight). */
  getRowClassName?: (row: T) => string | undefined;
  /** Row click handler (e.g. select-for-detail). */
  onRowClick?: (row: T) => void;
  /** Extra controls placed in the toolbar next to the search box. */
  toolbarExtras?: ReactNode;
  /** Allow cells to wrap instead of single-line ellipsis (grid mode). */
  wrapCells?: boolean;
};

type TableProps<T> = CommonProps<T> & {
  /**
   * `"table"` renders a semantic `<table>` (no virtualization) — correct a11y/roles for small,
   * static, or screen-reader-sensitive lists. `"grid"` renders a virtualized div CSS-grid
   * (TanStack Virtual windowing + ARIA grid roles) for genuinely large lists. Default `"grid"`
   * preserves the original behaviour for existing callers.
   */
  as?: "table" | "grid";
  /** Compact density in `as="table"` mode (reuses `.table.compact`). */
  compact?: boolean;
  /**
   * Suppress the `<thead>` in `as="table"` mode — for headerless key/value
   * tables whose columns carry no meaningful header label. No effect in grid mode.
   */
  hideHeader?: boolean;
  /** grid-mode scroll viewport height. */
  height?: number;
  /** grid-mode estimated row height. */
  rowHeight?: number;
};

const sortIndicator = (dir: false | "asc" | "desc") =>
  dir === "asc" ? " ▲" : dir === "desc" ? " ▼" : "";

const ariaSort = (dir: false | "asc" | "desc"): "ascending" | "descending" | "none" =>
  dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none";

/**
 * Shared admin table (T-254, extended T-270). TanStack **Table** drives column defs,
 * global-filter search and click-to-sort in BOTH modes; TanStack **Virtual** windows rows in
 * `as="grid"` mode. `as="table"` mode renders a real semantic `<table>` (caption + `<th scope>`)
 * for the many small/a11y-sensitive admin lists. The declarative `VirtualColumn<T>` API
 * (key/header/cell/sortValue/align/headerCell/width) plus row hooks (getRowClassName/onRowClick),
 * `toolbarExtras`, and selection-via-column-cells cover every admin surface.
 */
export function VirtualTable<T>({
  rows,
  columns,
  rowKey,
  getSearchText,
  searchPlaceholder = "검색",
  emptyHint = "결과가 없습니다.",
  initialSortKey = null,
  initialSortDir = "asc",
  caption,
  getRowClassName,
  onRowClick,
  toolbarExtras,
  wrapCells = false,
  as = "grid",
  compact = false,
  hideHeader = false,
  height = 360,
  rowHeight = 44
}: TableProps<T>) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>(
    initialSortKey ? [{ id: initialSortKey, desc: initialSortDir === "desc" }] : []
  );

  const columnDefs = useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((c) => ({
        id: c.key,
        header: c.header,
        accessorFn: c.sortValue ? (row) => c.sortValue?.(row) : undefined,
        enableSorting: Boolean(c.sortValue),
        // First click always ascending (react-table defaults numeric columns to desc-first).
        sortDescFirst: false,
        sortUndefined: "last",
        cell: (info) => c.cell(info.row.original)
      })),
    [columns]
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    state: { globalFilter, sorting },
    onGlobalFilterChange: setGlobalFilter,
    onSortingChange: setSorting,
    enableGlobalFilter: Boolean(getSearchText),
    globalFilterFn: getSearchText
      ? (row, _columnId, value) =>
          getSearchText(row.original).toLowerCase().includes(String(value).toLowerCase())
      : "includesString",
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getRowId: (row) => rowKey(row)
  });

  const modelRows = table.getRowModel().rows;
  const colByKey = useMemo(() => new Map(columns.map((c) => [c.key, c])), [columns]);
  const headers = table.getHeaderGroups()[0]?.headers ?? [];

  // Virtualizer must be called unconditionally (hook rules); only used in grid mode.
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: as === "grid" ? modelRows.length : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8
  });

  const showToolbar = Boolean(getSearchText) || Boolean(toolbarExtras);
  const toolbar = showToolbar ? (
    <div className="vtable-toolbar">
      {getSearchText ? (
        <input
          aria-label="목록 검색"
          className="vtable-search"
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder={searchPlaceholder}
          value={globalFilter}
        />
      ) : (
        <span />
      )}
      <div className="vtable-toolbar-end">
        {toolbarExtras}
        {getSearchText ? (
          <span className="vtable-count">
            {modelRows.length} / {rows.length}
          </span>
        ) : null}
      </div>
    </div>
  ) : null;

  function headerButton(header: (typeof headers)[number]): ReactNode {
    const col = colByKey.get(header.column.id);
    if (col?.headerCell !== undefined) return col.headerCell;
    const canSort = header.column.getCanSort();
    const sorted = header.column.getIsSorted();
    if (!canSort) {
      return flexRender(header.column.columnDef.header, header.getContext());
    }
    return (
      <button
        className="vtable-th-sort"
        onClick={header.column.getToggleSortingHandler()}
        type="button"
      >
        {flexRender(header.column.columnDef.header, header.getContext())}
        {sortIndicator(sorted)}
      </button>
    );
  }

  if (as === "table") {
    return (
      <div className="vtable-static">
        {toolbar}
        <table className={compact ? "table compact" : "table"}>
          {caption ? <caption className="vtable-caption">{caption}</caption> : null}
          {hideHeader ? null : (
            <thead>
              <tr>
                {headers.map((header) => {
                  const col = colByKey.get(header.column.id);
                  return (
                    <th
                      aria-sort={
                        header.column.getCanSort()
                          ? ariaSort(header.column.getIsSorted())
                          : undefined
                      }
                      key={header.id}
                      scope="col"
                      style={col?.align ? { textAlign: col.align } : undefined}
                    >
                      {headerButton(header)}
                    </th>
                  );
                })}
              </tr>
            </thead>
          )}
          <tbody>
            {modelRows.length === 0 ? (
              <tr>
                <td className="vtable-empty" colSpan={columns.length}>
                  {emptyHint}
                </td>
              </tr>
            ) : (
              modelRows.map((row) => (
                <tr
                  className={getRowClassName?.(row.original) || undefined}
                  key={row.id}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => {
                    const col = colByKey.get(cell.column.id);
                    const style = col?.align ? { textAlign: col.align } : undefined;
                    const content = flexRender(cell.column.columnDef.cell, cell.getContext());
                    return col?.rowHeader ? (
                      <th className={col.cellClassName} key={cell.id} scope="row" style={style}>
                        {content}
                      </th>
                    ) : (
                      <td className={col?.cellClassName} key={cell.id} style={style}>
                        {content}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    );
  }

  // grid mode (virtualized div CSS-grid + ARIA grid roles)
  const gridTemplate = columns.map((c) => c.width ?? "1fr").join(" ");
  return (
    <div className={wrapCells ? "vtable vtable-wrap" : "vtable"}>
      {toolbar ?? (
        <div className="vtable-toolbar">
          <span />
          <span className="vtable-count">
            {modelRows.length} / {rows.length}
          </span>
        </div>
      )}
      <div className="vtable-grid">
        <div className="vtable-head" style={{ gridTemplateColumns: gridTemplate }}>
          {headers.map((header) => {
            const col = colByKey.get(header.column.id);
            const canSort = header.column.getCanSort();
            return (
              <div
                aria-sort={canSort ? ariaSort(header.column.getIsSorted()) : undefined}
                className="vtable-th"
                key={header.id}
                style={col?.align ? { textAlign: col.align } : undefined}
              >
                {headerButton(header)}
              </div>
            );
          })}
        </div>
        <div className="vtable-body" ref={parentRef} style={{ height }}>
          {modelRows.length === 0 ? (
            <p className="wizard-hint">{emptyHint}</p>
          ) : (
            <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
              {virtualizer.getVirtualItems().map((item) => {
                const row = modelRows[item.index] as Row<T>;
                const rowClassName = getRowClassName?.(row.original);
                const rowClickProps = onRowClick
                  ? {
                      onClick: () => onRowClick(row.original),
                      onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowClick(row.original);
                        }
                      },
                      tabIndex: 0
                    }
                  : {};
                return (
                  <div
                    className={`vtable-row${rowClassName ? ` ${rowClassName}` : ""}`}
                    data-clickable={onRowClick ? true : undefined}
                    key={row.id}
                    {...rowClickProps}
                    style={{
                      gridTemplateColumns: gridTemplate,
                      height: item.size,
                      left: 0,
                      position: "absolute",
                      top: 0,
                      transform: `translateY(${item.start}px)`,
                      width: "100%"
                    }}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const col = colByKey.get(cell.column.id);
                      return (
                        <div
                          className={col?.cellClassName ? `vtable-td ${col.cellClassName}` : "vtable-td"}
                          key={cell.id}
                          style={col?.align ? { textAlign: col.align } : undefined}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
