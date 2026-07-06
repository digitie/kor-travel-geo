"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AdminTabs, AdminTabsContent } from "@/components/admin/shared/AdminTabs";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { requestJson } from "@/lib/api";
import {
  sourceFilesPaths,
  type ConsistencyCaseDefinition,
  type ConsistencyReport,
  type ConsistencyReportSummary
} from "@/lib/source-files";

const EMPTY_DEFINITIONS: ConsistencyCaseDefinition[] = [];

/**
 * Dynamic consistency-case display (T-206 UI part).
 *
 * Reads the case registry from ``GET /admin/consistency/case-definitions``
 * (C1~C17, the DB registry being the source of truth) instead of hardcoding
 * C1~C10. The latest report's per-case severity/count comes from the report
 * object, whose ``cases`` the backend already builds from the same registry, so
 * new C11+ cases appear automatically without any UI change.
 */
export function SourceCasesTab() {
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const { data: definitions = EMPTY_DEFINITIONS } = useQuery({
    queryKey: ["consistency-case-definitions"],
    queryFn: () =>
      requestJson<ConsistencyCaseDefinition[]>(sourceFilesPaths.consistencyCaseDefinitions())
  });
  const { data: reports = [] } = useQuery({
    queryKey: ["consistency-reports"],
    queryFn: () => requestJson<ConsistencyReportSummary[]>(sourceFilesPaths.consistency())
  });
  const latestReportId = reports[0]?.report_id ?? null;
  const { data: report } = useQuery({
    queryKey: ["consistency-report", latestReportId],
    queryFn: () => requestJson<ConsistencyReport>(sourceFilesPaths.consistencyReport(latestReportId!)),
    enabled: latestReportId !== null
  });

  const caseByCode = useMemo(
    () => new Map((report?.cases ?? []).map((item) => [item.code, item])),
    [report?.cases]
  );

  const effectiveCode = selectedCode ?? definitions[0]?.code ?? null;
  const selectedDefinition = definitions.find((item) => item.code === effectiveCode);
  const selectedCase = effectiveCode ? caseByCode.get(effectiveCode) : undefined;

  const tabItems = useMemo(
    () =>
      definitions.map((definition) => {
        const caseRow = caseByCode.get(definition.code);
        return {
          value: definition.code,
          label: (
            <>
              <strong>{definition.code}</strong>
              <span>{definition.name}</span>
              {caseRow ? <StatusBadge value={caseRow.severity} /> : null}
              {caseRow ? <small>{caseRow.count.toLocaleString()}건</small> : null}
            </>
          )
        };
      }),
    [definitions, caseByCode]
  );

  return (
    <Panel
      title="검증 케이스"
      badges={<Badge tone="neutral">{definitions.length}개</Badge>}
    >
      {definitions.length === 0 ? (
        <EmptyState>케이스 정의를 불러오는 중…</EmptyState>
      ) : (
        <AdminTabs
          items={tabItems}
          label="검증 케이스"
          onValueChange={setSelectedCode}
          value={effectiveCode ?? ""}
        >
          <AdminTabsContent className="analysis-pane" value={effectiveCode ?? ""}>
            {selectedDefinition ? (
              <div className="criteria-panel">
                <div>
                  <h3>
                    {selectedDefinition.code} {selectedDefinition.name}
                  </h3>
                  <p>{selectedDefinition.compares}</p>
                </div>
                <KeyValueGrid
                  items={[
                    { label: "비정상 기준", value: selectedDefinition.abnormal_criteria },
                    { label: "판정 가이드", value: selectedDefinition.decision_guide },
                    { label: "증거", value: selectedDefinition.evidence.join(", ") || "-" },
                    {
                      label: "최근 결과",
                      value: selectedCase
                        ? `${selectedCase.severity} · ${selectedCase.count.toLocaleString()}건`
                        : "최근 보고서에 없음"
                    }
                  ]}
                />
                <p className="form-note">
                  상세 sample 분석과 수동 판정은{" "}
                  <DocumentNavLink className="link-button" href="/admin/consistency">
                    정합성(Consistency) 화면
                  </DocumentNavLink>
                  에서 진행합니다.
                </p>
              </div>
            ) : (
              <EmptyState>표시할 케이스 정의가 없습니다.</EmptyState>
            )}
          </AdminTabsContent>
        </AdminTabs>
      )}
    </Panel>
  );
}
