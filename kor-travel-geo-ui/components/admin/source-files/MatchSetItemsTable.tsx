"use client";

import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { sourceRoleLabel, type SourceMatchSetItem } from "@/lib/source-files";

const SUMMARY_COLUMNS: VirtualColumn<SourceMatchSetItem>[] = [
  { key: "category", header: "카테고리", cell: (item) => item.category },
  { key: "role", header: "역할", cell: (item) => sourceRoleLabel(item.role) },
  { key: "omitted", header: "생략", cell: (item) => (item.omitted ? "생략" : "포함") },
  {
    key: "group",
    header: "그룹 ID",
    cell: (item) => (item.source_file_group_id ? `${item.source_file_group_id.slice(0, 12)}…` : "-")
  }
];

const ACTIVE_COLUMNS: VirtualColumn<SourceMatchSetItem>[] = [
  { key: "category", header: "카테고리", cell: (item) => item.category },
  { key: "role", header: "역할", cell: (item) => sourceRoleLabel(item.role) },
  { key: "effective", header: "기준월", cell: (item) => item.effective_yyyymm ?? "-" },
  { key: "omitted", header: "포함", cell: (item) => (item.omitted ? "생략" : "포함") },
  {
    key: "group",
    header: "그룹",
    cell: (item) =>
      item.source_file_group_id ? (
        `${item.source_file_group_id.slice(0, 12)}…`
      ) : (
        <span className="form-note">source_file_unavailable</span>
      )
  }
];

const DETAIL_COLUMNS: VirtualColumn<SourceMatchSetItem>[] = [
  { key: "category", header: "카테고리", cell: (item) => item.category },
  { key: "role", header: "역할", cell: (item) => sourceRoleLabel(item.role) },
  { key: "omitted", header: "생략", cell: (item) => (item.omitted ? "생략" : "포함") },
  { key: "effective", header: "기준월", cell: (item) => item.effective_yyyymm ?? "-" },
  {
    key: "group",
    header: "그룹 ID",
    cell: (item) => (item.source_file_group_id ? `${item.source_file_group_id.slice(0, 12)}…` : "-")
  }
];

const COLS: Record<"summary" | "active" | "detail", VirtualColumn<SourceMatchSetItem>[]> = {
  summary: SUMMARY_COLUMNS,
  active: ACTIVE_COLUMNS,
  detail: DETAIL_COLUMNS
};

export function MatchSetItemsTable({
  items,
  variant
}: {
  items: SourceMatchSetItem[];
  variant: "summary" | "active" | "detail";
}) {
  return (
    <VirtualTable
      as="table"
      columns={COLS[variant]}
      compact
      rowKey={(i) => i.source_match_set_item_id}
      rows={items}
    />
  );
}
