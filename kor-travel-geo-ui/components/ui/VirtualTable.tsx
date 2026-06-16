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
  type SortingState,
  useReactTable
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { type ReactNode, useMemo, useRef, useState } from "react";

export type VirtualColumn<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Provide to make the column sortable (click the header to toggle asc/desc). */
  sortValue?: (row: T) => string | number | null | undefined;
  /** CSS grid track for this column (default ``1fr``). */
  width?: string;
};

/**
 * Shared admin list (T-254): TanStack **Table** drives column defs, global-filter search, and
 * click-to-sort; TanStack **Virtual** windows the (filtered+sorted) rows so artifacts/jobs/
 * sessions/reconcile lists stay responsive at thousands of rows. Reused by T-226 and other
 * admin surfaces. The ``VirtualColumn<T>`` API stays declarative (key/header/cell/sortValue).
 */
export function VirtualTable<T>({
  rows,
  columns,
  rowKey,
  getSearchText,
  searchPlaceholder = "검색",
  height = 360,
  rowHeight = 44,
  emptyHint = "결과가 없습니다.",
  initialSortKey = null,
  initialSortDir = "asc"
}: {
  rows: T[];
  columns: VirtualColumn<T>[];
  rowKey: (row: T) => string;
  getSearchText?: (row: T) => string;
  searchPlaceholder?: string;
  height?: number;
  rowHeight?: number;
  emptyHint?: string;
  initialSortKey?: string | null;
  initialSortDir?: "asc" | "desc";
}) {
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
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: modelRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8
  });

  const gridTemplate = columns.map((c) => c.width ?? "1fr").join(" ");
  const headers = table.getHeaderGroups()[0]?.headers ?? [];

  return (
    <div className="vtable">
      <div className="vtable-toolbar">
        {getSearchText ? (
          <input
            aria-label="목록 검색"
            className="vtable-search"
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder={searchPlaceholder}
            value={globalFilter}
          />
        ) : null}
        <span className="vtable-count">
          {modelRows.length} / {rows.length}
        </span>
      </div>
      <div className="vtable-head" style={{ gridTemplateColumns: gridTemplate }}>
        {headers.map((header) => {
          const sorted = header.column.getIsSorted();
          return (
            <button
              className={header.column.getCanSort() ? "vtable-th sortable" : "vtable-th"}
              disabled={!header.column.getCanSort()}
              key={header.id}
              onClick={header.column.getToggleSortingHandler()}
              type="button"
            >
              {flexRender(header.column.columnDef.header, header.getContext())}
              {sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}
            </button>
          );
        })}
      </div>
      <div className="vtable-body" ref={parentRef} style={{ height }}>
        {modelRows.length === 0 ? (
          <p className="wizard-hint">{emptyHint}</p>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = modelRows[item.index];
              return (
                <div
                  className="vtable-row"
                  key={row.id}
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
                  {row.getVisibleCells().map((cell) => (
                    <div className="vtable-td" key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
