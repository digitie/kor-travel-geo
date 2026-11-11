"use client";
import { useMemo, useState, type ReactNode } from "react";
import { VirtualTable as SharedVirtualTable, type ColumnDef, type HeaderContext, type RowData } from "@kor-travel/ui/virtual-table";
import { Input } from "@kor-travel/ui/input";

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
  /** 가상화 열의 fr 너비 비율. 공통 표의 픽셀 너비 모델로 변환한다. */
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
   * 두 모드 모두 공통 시맨틱 table을 사용한다.
   * table은 전체 행을, 기존 grid 옵션은 TanStack Virtual의 가시 행만 렌더한다.
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


// 공통 TanStack 열 기본 너비를 1fr 단위로 삼아 기존 비율을 보존한다.
const FRACTION_COLUMN_WIDTH_PX = 150;

// 헤더 표현은 meta로 전달하고 컴포넌트 참조를 유지해 입력·포커스 재생성을 막는다.
function ColumnHeader<T extends RowData>({ column }: HeaderContext<T>) {
 const meta = column.columnDef.meta as { geoHeaderCell?: ReactNode } | undefined;
 return meta?.geoHeaderCell ?? null;
}

/** Geo 열 표현을 공통 표 계약으로 변환한다. 정렬·렌더링·가상화 엔진은 common 소유다. */
export function VirtualTable<T extends RowData>({
 rows, columns, rowKey, getSearchText, searchPlaceholder = "검색",
 emptyHint = "결과가 없습니다.", initialSortKey, initialSortDir = "asc",
 caption, getRowClassName, onRowClick, toolbarExtras, wrapCells = false,
 as = "grid", compact = false, hideHeader = false, height = 360, rowHeight = 44
}: TableProps<T>) {
 const [query, setQuery] = useState("");
 const filtered = useMemo(() => getSearchText && query
   ? rows.filter(row => getSearchText(row).toLowerCase().includes(query.toLowerCase())) : rows,
   [rows, getSearchText, query]);
 const sharedColumns = useMemo(() => columns.map<ColumnDef<T, unknown>>(column => {
   const fraction = column.width?.endsWith("fr") ? Number(column.width.slice(0, -2)) : Number.NaN;
   const meta = { align: column.align, cellClassName: column.cellClassName, rowHeader: column.rowHeader, geoHeaderCell: column.headerCell };
   return {
    id: column.key,
    header: column.headerCell === undefined ? column.header : ColumnHeader,
    accessorFn: row => column.sortValue?.(row),
    enableSorting: Boolean(column.sortValue) && column.headerCell === undefined,
    sortDescFirst: false,
    sortUndefined: "last",
    size: Number.isFinite(fraction) && fraction > 0 ? fraction * FRACTION_COLUMN_WIDTH_PX : undefined,
    cell: context => column.cell(context.row.original),
    meta
   };
 }), [columns]);
 return <div className={compact ? "vtable-static compact" : "vtable-static"}>
   {getSearchText || toolbarExtras ? <div className="vtable-toolbar">
    {getSearchText ? <Input aria-label="목록 검색" value={query} onChange={event => setQuery(event.target.value)} placeholder={searchPlaceholder} /> : <span />}
    <div className="vtable-toolbar-end">{toolbarExtras}{getSearchText ? <span className="vtable-count">{filtered.length} / {rows.length}</span> : null}</div>
   </div> : null}
   <SharedVirtualTable data={filtered} columns={sharedColumns} getRowId={rowKey}
    manualSorting={false} initialSorting={initialSortKey ? [{id: initialSortKey, desc: initialSortDir === "desc"}] : []}
    caption={caption} ariaLabel={caption} containerClassName="vtable-scroll" emptyMessage={emptyHint}
    virtualized={as === "grid"} height={height} estimateRowSize={rowHeight}
    hideHeader={hideHeader} wrapCells={wrapCells} onRowClick={onRowClick}
    renderCell={(row, columnId) => columns.find(column => column.key === columnId)?.cell(row)}
    rowProps={row => ({ className: getRowClassName?.(row) })} />
 </div>;
}
