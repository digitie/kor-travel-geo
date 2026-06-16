"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { requestJson } from "@/lib/api";
import {
  diffMatchSets,
  type ItemDiffStatus,
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

  const detailA = useQuery({
    queryKey: ["source-match-set", effectiveA],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(effectiveA)),
    enabled: Boolean(effectiveA)
  });
  const detailB = useQuery({
    queryKey: ["source-match-set", effectiveB],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(effectiveB)),
    enabled: Boolean(effectiveB)
  });

  const diff =
    detailA.data && detailB.data && effectiveA !== effectiveB
      ? diffMatchSets(detailA.data, detailB.data)
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

          <table className="table compact">
            <tbody>
              {diff.setMeta.map((row) => (
                <tr key={row.field} className={row.changed ? "compare-changed" : undefined}>
                  <th>{row.field}</th>
                  <td>{row.a ?? "-"}</td>
                  <td>{row.b ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <table className="table compact">
            <thead>
              <tr>
                <th>카테고리</th>
                <th>상태</th>
                <th>A (역할·기준월·그룹)</th>
                <th>B (역할·기준월·그룹)</th>
              </tr>
            </thead>
            <tbody>
              {diff.items.map((item) => (
                <tr key={item.category} className={item.status !== "same" ? "compare-changed" : undefined}>
                  <td>{item.category}</td>
                  <td>
                    <StatusBadge tone={STATUS_TONE[item.status]} value={STATUS_LABEL[item.status]} />
                  </td>
                  <td>
                    <ItemCell changed={item.changedFields} item={item.a} />
                  </td>
                  <td>
                    <ItemCell changed={item.changedFields} item={item.b} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
