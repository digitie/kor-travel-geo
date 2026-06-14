"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
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

  return (
    <Panel title={`검증 케이스 (${definitions.length}개 · registry 기준)`}>
      <nav aria-label="검증 케이스 선택" className="case-tabs">
        <div aria-label="검증 케이스" aria-orientation="horizontal" className="case-tab-list" role="tablist">
          {definitions.map((definition) => {
            const isSelected = definition.code === effectiveCode;
            const caseRow = caseByCode.get(definition.code);
            return (
              <button
                aria-controls="source-case-panel"
                aria-selected={isSelected}
                className={isSelected ? "case-tab active" : "case-tab"}
                id={`source-case-tab-${definition.code}`}
                key={definition.code}
                onClick={() => setSelectedCode(definition.code)}
                role="tab"
                type="button"
              >
                <strong>{definition.code}</strong>
                <span>{definition.name}</span>
                {caseRow ? <StatusBadge value={caseRow.severity} /> : null}
                {caseRow ? <small>{caseRow.count.toLocaleString()}건</small> : null}
              </button>
            );
          })}
          {definitions.length === 0 ? <p className="form-note">케이스 정의를 불러오는 중…</p> : null}
        </div>
      </nav>

      <section
        aria-labelledby={`source-case-tab-${effectiveCode ?? "none"}`}
        className="analysis-pane"
        id="source-case-panel"
        role="tabpanel"
      >
        {selectedDefinition ? (
          <div className="criteria-panel">
            <div>
              <h3>
                {selectedDefinition.code} {selectedDefinition.name}
              </h3>
              <p>{selectedDefinition.compares}</p>
            </div>
            <dl className="criteria-grid">
              <div>
                <dt>비정상 기준</dt>
                <dd>{selectedDefinition.abnormal_criteria}</dd>
              </div>
              <div>
                <dt>판정 가이드</dt>
                <dd>{selectedDefinition.decision_guide}</dd>
              </div>
              <div>
                <dt>증거</dt>
                <dd>{selectedDefinition.evidence.join(", ") || "-"}</dd>
              </div>
              <div>
                <dt>최근 결과</dt>
                <dd>
                  {selectedCase
                    ? `${selectedCase.severity} · ${selectedCase.count.toLocaleString()}건`
                    : "최근 보고서에 없음"}
                </dd>
              </div>
            </dl>
            <p className="form-note">
              상세 sample 분석과 수동 판정은{" "}
              <DocumentNavLink className="link-button" href="/admin/consistency">
                정합성(Consistency) 화면
              </DocumentNavLink>
              에서 진행합니다.
            </p>
          </div>
        ) : (
          <p className="form-note">표시할 케이스 정의가 없습니다.</p>
        )}
      </section>
    </Panel>
  );
}
