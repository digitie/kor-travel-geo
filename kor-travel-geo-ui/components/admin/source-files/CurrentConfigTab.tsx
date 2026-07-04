"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { MatchSetItemsTable } from "@/components/admin/source-files/MatchSetItemsTable";
import { JsonBlock } from "@/components/ui/JsonBlock";
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
          <KeyValueGrid
            items={[
              {
                label: "활성 릴리스",
                value: `${activeRelease.serving_release_id} · ${activeRelease.activated_at ?? "-"}`,
                help: (
                  <>
                    API 필드 <code>serving_release_id</code> / <code>activated_at</code>
                  </>
                ),
                helpLabel: "활성 릴리스 도움말"
              },
              {
                label: "릴리스 종류",
                value: activeRelease.release_kind,
                help: (
                  <>
                    API 필드 <code>release_kind</code>
                  </>
                ),
                helpLabel: "릴리스 종류 도움말"
              },
              {
                label: "데이터셋 스냅샷",
                value: activeRelease.dataset_snapshot_id,
                help: (
                  <>
                    API 필드 <code>dataset_snapshot_id</code>
                  </>
                ),
                helpLabel: "데이터셋 스냅샷 도움말"
              },
              {
                label: "정합성",
                value: activeSnapshot?.consistency_report_id ?? "-",
                help: (
                  <>
                    API 필드 <code>consistency_report_id</code> — 이 스냅샷을 승인한 정합성
                    보고서
                  </>
                ),
                helpLabel: "정합성 도움말"
              }
            ]}
          />
        ) : (
          <p className="form-note">활성 serving release가 없습니다.</p>
        )}
      </Panel>

      <Panel title="DB를 만든 원천 매칭 정보">
        {active ? (
          <ActiveMatchSetView detail={detail} matchSet={active} />
        ) : estimated ? (
          <div className="confirm-box">
            <div className="confirm-title flex items-center gap-1">
              <StatusBadge value="추정" /> match set 정본 없음
              <HelpTip label="추정 도움말">
                FK 경로(serving_releases → dataset_snapshots.source_match_set_id)에서 match set
                연결을 찾지 못해 snapshot의 source_set JSONB에서 추정했습니다 (정본으로 저장하지
                않음).
              </HelpTip>
            </div>
            <p className="form-note">
              match set 기록이 없어 snapshot 정보에서 추정한 값입니다.
            </p>
            <JsonBlock value={activeSnapshot?.source_set ?? {}} />
          </div>
        ) : (
          <div className="confirm-box">
            <div className="confirm-title">현재 DB를 만든 원천 매칭 정보: 알수없음</div>
            <p className="form-note">
              match set 도입 전에 만들어진 DB이거나, 백업 복원 과정에서 match set metadata가
              없습니다.
            </p>
          </div>
        )}
      </Panel>

      {restored ? (
        <Panel
          title="백업 복원 매칭 세트"
          badges={
            <HelpTip label="백업 복원 매칭 세트 도움말">
              상태 <code>restored_from_backup</code> — 백업 manifest에서 복원된 stub 세트입니다.
              <code>group_sha256</code>는 복원 manifest에서 온 UNTRUSTED metadata입니다.
            </HelpTip>
          }
        >
          <div className="confirm-box" role="alert">
            <div className="confirm-title">
              <AlertTriangle size={14} /> {restored.name}
            </div>
            <p className="form-note">
              백업 manifest에서 복원된 stub 매칭 세트입니다. 모든 참조 그룹을 relink해
              사용 가능(available) 상태가 되기 전까지 rebuild는 비활성입니다.
            </p>
            <KeyValueGrid
              items={[
                { label: "상태", value: matchSetStateLabels[restored.state] },
                {
                  label: "구성 해시",
                  value: shortHash(restored.source_set_hash),
                  help: (
                    <>
                      API 필드 <code>source_set_hash</code>
                    </>
                  ),
                  helpLabel: "구성 해시 도움말"
                }
              ]}
            />
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
      <KeyValueGrid
        items={[
          {
            label: "이름 / id",
            value: `${matchSet.name} · ${matchSet.source_match_set_id.slice(0, 12)}…`
          },
          {
            label: "프로파일",
            value: matchSet.profile,
            help: (
              <>
                API 필드 <code>profile</code>
              </>
            ),
            helpLabel: "프로파일 도움말"
          },
          {
            label: "상태",
            value: <StatusBadge value={matchSetStateLabels[matchSet.state]} />
          },
          {
            label: "구성 해시",
            value: shortHash(matchSet.source_set_hash),
            help: (
              <>
                API 필드 <code>source_set_hash</code>
              </>
            ),
            helpLabel: "구성 해시 도움말"
          }
        ]}
      />
      {matchSet.integrity_alert ? (
        <p className="form-note warn">
          <AlertTriangle size={13} /> 활성 세트에 무결성 경보(integrity_alert)가 있습니다.
        </p>
      ) : null}
      <MatchSetItemsTable items={detail?.items ?? []} variant="active" />
    </>
  );
}
