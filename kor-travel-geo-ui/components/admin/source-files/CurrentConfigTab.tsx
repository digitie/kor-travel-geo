"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { requestJson } from "@/lib/api";
import {
  matchSetStateLabels,
  shortHash,
  sourceFilesPaths,
  type DatasetSnapshot,
  type ServingRelease,
  type SourceMatchSet,
  type SourceMatchSetDetail
} from "@/lib/source-files";

const EMPTY_SETS: SourceMatchSet[] = [];

export function CurrentConfigTab() {
  const { data: matchSets = EMPTY_SETS } = useQuery({
    queryKey: ["source-match-sets"],
    queryFn: () => requestJson<SourceMatchSet[]>(sourceFilesPaths.matchSets())
  });
  const { data: releases = [] } = useQuery({
    queryKey: ["serving-releases"],
    queryFn: () => requestJson<ServingRelease[]>(sourceFilesPaths.servingReleases())
  });
  const { data: snapshots = [] } = useQuery({
    queryKey: ["dataset-snapshots"],
    queryFn: () => requestJson<DatasetSnapshot[]>(sourceFilesPaths.snapshots())
  });

  const active = matchSets.find((set) => set.state === "active") ?? null;
  const restored = matchSets.find((set) => set.state === "restored_from_backup") ?? null;
  const activeRelease = releases.find((release) => release.state === "active") ?? releases[0] ?? null;

  const { data: detail } = useQuery({
    queryKey: ["source-match-set", active?.source_match_set_id],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(active!.source_match_set_id)),
    enabled: Boolean(active?.source_match_set_id)
  });

  // 현재 구성 조회 순서: serving_releases → dataset_snapshots.source_match_set_id → source_match_sets
  // FK 경로에서 match set을 찾지 못하면 "알수없음", JSONB 추정 정보가 있으면 "추정" 배지.
  const activeSnapshot = activeRelease
    ? snapshots.find(
        (snapshot) => snapshot.dataset_snapshot_id === activeRelease.dataset_snapshot_id,
      ) ?? null
    : null;
  const estimated = !active && Boolean(activeSnapshot?.source_set);

  return (
    <div className="source-stack">
      <Panel title="현재 serving 구성">
        {activeRelease ? (
          <dl className="criteria-grid">
            <div>
              <dt>active release</dt>
              <dd>
                {activeRelease.serving_release_id} · {activeRelease.activated_at ?? "-"}
              </dd>
            </div>
            <div>
              <dt>release kind</dt>
              <dd>{activeRelease.release_kind}</dd>
            </div>
            <div>
              <dt>dataset snapshot</dt>
              <dd>{activeRelease.dataset_snapshot_id}</dd>
            </div>
            <div>
              <dt>정합성</dt>
              <dd>{activeSnapshot?.consistency_report_id ?? "-"}</dd>
            </div>
          </dl>
        ) : (
          <p className="form-note">활성 serving release가 없습니다.</p>
        )}
      </Panel>

      <Panel title="DB를 만든 원천 매칭 정보">
        {active ? (
          <ActiveMatchSetView detail={detail} matchSet={active} />
        ) : estimated ? (
          <div className="confirm-box">
            <label>
              <StatusBadge value="추정" /> match set 정본 없음
            </label>
            <p className="form-note">
              FK 경로(serving_releases → dataset_snapshots.source_match_set_id)에서 match set 연결을
              찾지 못했습니다. snapshot의 source_set JSONB에서 추정한 정보입니다 (정본으로 저장하지 않음).
            </p>
            <pre className="json-box compact-json">
              {JSON.stringify(activeSnapshot?.source_set ?? {}, null, 2)}
            </pre>
          </div>
        ) : (
          <div className="confirm-box">
            <label>현재 DB를 만든 원천 매칭 정보: 알수없음</label>
            <p className="form-note">
              이 DB는 T-109 source match set 도입 전에 생성되었거나, 백업 복원 과정에서 match set
              metadata가 없습니다.
            </p>
          </div>
        )}
      </Panel>

      {restored ? (
        <Panel title="백업 복원 매칭 세트 (restored_from_backup)">
          <div className="confirm-box" role="alert">
            <label>
              <AlertTriangle size={14} /> {restored.name}
            </label>
            <p className="form-note">
              백업 manifest에서 복원된 stub 매칭 세트입니다. 모든 참조 그룹이 relink되어 `available`이
              되기 전까지 rebuild는 비활성입니다. group_sha256는 UNTRUSTED metadata입니다.
            </p>
            <dl className="criteria-grid">
              <div>
                <dt>상태</dt>
                <dd>{matchSetStateLabels[restored.state]}</dd>
              </div>
              <div>
                <dt>source_set_hash</dt>
                <dd>{shortHash(restored.source_set_hash)}</dd>
              </div>
            </dl>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function ActiveMatchSetView({
  matchSet,
  detail
}: {
  matchSet: SourceMatchSet;
  detail?: SourceMatchSetDetail;
}) {
  return (
    <>
      <dl className="criteria-grid">
        <div>
          <dt>이름 / id</dt>
          <dd>
            {matchSet.name} · {matchSet.source_match_set_id.slice(0, 12)}…
          </dd>
        </div>
        <div>
          <dt>profile</dt>
          <dd>{matchSet.profile}</dd>
        </div>
        <div>
          <dt>상태</dt>
          <dd>
            <StatusBadge value={matchSetStateLabels[matchSet.state]} />
          </dd>
        </div>
        <div>
          <dt>group hash</dt>
          <dd>{shortHash(matchSet.source_set_hash)}</dd>
        </div>
      </dl>
      {matchSet.integrity_alert ? (
        <p className="form-note warn">
          <AlertTriangle size={13} /> 활성 세트에 무결성 경보(integrity_alert)가 있습니다.
        </p>
      ) : null}
      <table className="table compact">
        <thead>
          <tr>
            <th>카테고리</th>
            <th>역할</th>
            <th>기준월</th>
            <th>포함</th>
            <th>그룹</th>
          </tr>
        </thead>
        <tbody>
          {(detail?.items ?? []).map((item) => (
            <tr key={item.source_match_set_item_id}>
              <td>{item.category}</td>
              <td>{item.role}</td>
              <td>{item.effective_yyyymm ?? "-"}</td>
              <td>{item.omitted ? "생략" : "포함"}</td>
              <td>
                {item.source_file_group_id ? (
                  `${item.source_file_group_id.slice(0, 12)}…`
                ) : (
                  <span className="form-note">source_file_unavailable</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
