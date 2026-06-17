"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { requestJson } from "@/lib/api";
import {
  diffMatchSets,
  type ItemDiffStatus,
  type MatchSetFieldDiff,
  type MatchSetItemDiff
} from "@/lib/match-set-diff";
import {
  matchSetStateLabels,
  sourceFilesPaths,
  sourceRoleLabel,
  type SourceMatchSet,
  type SourceMatchSetDetail,
  type SourceMatchSetItem
} from "@/lib/source-files";

const STATUS_LABEL: Record<ItemDiffStatus, string> = {
  added: "추가",
  removed: "제거",
  changed: "변경",
  same: "동일"
};

const STATUS_TONE: Record<ItemDiffStatus, "ok" | "warn" | "error" | undefined> = {
  added: "ok",
  removed: "error",
  changed: "warn",
  same: undefined
};

// setmeta is a transposed key/value comparison (field → A | B), so it is headerless
// with the field rendered as a row header (<th scope="row">).
const SET_META_COLUMNS: VirtualColumn<MatchSetFieldDiff>[] = [
  { key: "field", header: "", rowHeader: true, cell: (row) => row.field },
  { key: "a", header: "", cell: (row) => row.a ?? "-" },
  { key: "b", header: "", cell: (row) => row.b ?? "-" }
];

const ITEM_DIFF_COLUMNS: VirtualColumn<MatchSetItemDiff>[] = [
  { key: "category", header: "카테고리", cell: (item) => item.category },
  {
    key: "status",
    header: "상태",
    cell: (item) => <StatusBadge tone={STATUS_TONE[item.status]} value={STATUS_LABEL[item.status]} />
  },
  {
    key: "a",
    header: "A (역할·기준월·그룹)",
    cell: (item) => <ItemCell changed={item.changedFields} item={item.a} />
  },
  {
    key: "b",
    header: "B (역할·기준월·그룹)",
    cell: (item) => <ItemCell changed={item.changedFields} item={item.b} />
  }
];

/**
 * T-226: 두 source match set을 비교(현재 구성 diff / match set 비교). 활성 세트를 기준(A)으로,
 * 다른 세트를 비교(B)로 골라 카테고리별 추가/제거/변경/동일과 set-level 필드 delta를 보여 준다.
 * 비교는 기존 per-id 상세 엔드포인트만 사용한 client-side diff라 백엔드 변경이 없다.
 */
export function MatchSetComparePanel({ matchSets }: { matchSets: SourceMatchSet[] }) {
  const sorted = useMemo(() => {
    const active = matchSets.filter((s) => s.state === "active");
    const rest = matchSets.filter((s) => s.state !== "active");
    return [...active, ...rest];
  }, [matchSets]);

  const [aId, setAId] = useState<string>("");
  const [bId, setBId] = useState<string>("");
  const effectiveA = aId || sorted[0]?.source_match_set_id || "";
  const effectiveB = bId || sorted.find((s) => s.source_match_set_id !== effectiveA)?.source_match_set_id || "";

  const { data: detailA } = useQuery({
    queryKey: ["source-match-set", effectiveA],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(effectiveA)),
    enabled: Boolean(effectiveA)
  });
  const { data: detailB } = useQuery({
    queryKey: ["source-match-set", effectiveB],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(effectiveB)),
    enabled: Boolean(effectiveB)
  });

  const diff =
    detailA && detailB && effectiveA !== effectiveB
      ? diffMatchSets(detailA, detailB)
      : null;

  return (
    <Panel title="매칭 세트 비교 (구성 diff)">
      <div className="form-grid compare-selectors">
        <label className="field">
          <span>기준 (A)</span>
          <select onChange={(e) => setAId(e.target.value)} value={effectiveA}>
            {sorted.map((s) => (
              <option key={s.source_match_set_id} value={s.source_match_set_id}>
                {s.name} · {matchSetStateLabels[s.state]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>비교 (B)</span>
          <select onChange={(e) => setBId(e.target.value)} value={effectiveB}>
            {sorted.map((s) => (
              <option key={s.source_match_set_id} value={s.source_match_set_id}>
                {s.name} · {matchSetStateLabels[s.state]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {sorted.length < 2 ? (
        <p className="form-note">비교하려면 매칭 세트가 2개 이상 필요합니다.</p>
      ) : effectiveA === effectiveB ? (
        <p className="form-note">같은 세트를 선택했습니다. 서로 다른 두 세트를 고르세요.</p>
      ) : !diff ? (
        <p className="form-note">상세를 불러오는 중…</p>
      ) : (
        <>
          <p className="compare-counts">
            <StatusBadge tone="ok" value={`추가 ${diff.counts.added}`} />{" "}
            <StatusBadge tone="error" value={`제거 ${diff.counts.removed}`} />{" "}
            <StatusBadge tone="warn" value={`변경 ${diff.counts.changed}`} />{" "}
            <span className="form-note">동일 {diff.counts.same}</span>
          </p>

          <VirtualTable
            as="table"
            columns={SET_META_COLUMNS}
            compact
            getRowClassName={(row) => (row.changed ? "compare-changed" : undefined)}
            hideHeader
            rowKey={(row) => row.field}
            rows={diff.setMeta}
          />

          <VirtualTable
            as="table"
            columns={ITEM_DIFF_COLUMNS}
            compact
            getRowClassName={(item) => (item.status !== "same" ? "compare-changed" : undefined)}
            rowKey={(item) => item.category}
            rows={diff.items}
          />
        </>
      )}
    </Panel>
  );
}

function ItemCell({
  item,
  changed
}: {
  item: SourceMatchSetItem | null;
  changed: MatchSetItemDiff["changedFields"];
}) {
  if (!item) return <span className="form-note">—</span>;
  const cls = (field: string) =>
    changed.includes(field as MatchSetItemDiff["changedFields"][number]) ? "compare-field-changed" : undefined;
  return (
    <span className="compare-item-cell">
      <span className={cls("role")}>{sourceRoleLabel(item.role)}</span>
      {" · "}
      <span className={cls("effective_yyyymm")}>{item.effective_yyyymm ?? "-"}</span>
      {" · "}
      <span className={cls("source_file_group_id")}>
        {item.source_file_group_id ? `${item.source_file_group_id.slice(0, 8)}…` : "없음"}
      </span>
      {changed.includes("omitted") ? (
        <small className={`form-note ${cls("omitted") ? "warn" : ""}`}>
          {" "}
          {item.omitted ? "생략" : "포함"}
        </small>
      ) : null}
    </span>
  );
}
