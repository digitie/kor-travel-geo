"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef
} from "@tanstack/react-table";
import { Check, Clock, Download, Play, RefreshCw, RotateCw, X } from "lucide-react";
import { useMemo, useState } from "react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { LazyCoordinateMap } from "@/components/vworld/LazyCoordinateMap";
import {
  API_BASE,
  backendPath,
  patchJson,
  postJson,
  requestJson,
  type ConsistencyBulkDecisionRequest,
  type ConsistencyCaseDefinition,
  type ConsistencyCaseSample,
  type ConsistencyCaseSummary,
  type ConsistencyDecisionState,
  type ConsistencyReport,
  type ConsistencyReportSummary,
  type ConsistencySampleDecisionRequest,
  type ConsistencySamplePage,
  type ConsistencySampleRecheckResponse,
  type LoadJobStatus
} from "@/lib/api";
import {
  consistencySamplesPath,
  decisionLabels,
  decisionReasons
} from "@/lib/consistency";
import { useConsistencyAnalysisStore } from "@/lib/stores/consistency-analysis-store";

type DecisionTarget = "single" | "bulk";
type ActionState = Exclude<ConsistencyDecisionState, "unreviewed">;

type DecisionForm = {
  target: DecisionTarget;
  state: ActionState;
  reasonCode: string;
  reviewer: string;
  note: string;
};

type SampleFilters = {
  severity: string;
  decision: string;
  sigCd: string;
  orderBy: string;
  desc: boolean;
  page: number;
};

const PAGE_SIZE = 50;

// Stable empty reference so `samples` doesn't get a brand-new array on every render
// while the samples query is loading. Passing a fresh `[]` into useReactTable on each
// render makes TanStack Table's auto-reset fire a state update every render, which spins
// React into an infinite re-render loop that pins the main thread and freezes the tab
// (notably when switching cases C1~C10, whose refetch leaves the data briefly undefined).
const EMPTY_SAMPLES: ConsistencyCaseSample[] = [];
const EMPTY_CASES: ConsistencyReport["cases"] = [];

export function ConsistencyPanel({ initialReportId = null }: { initialReportId?: string | null }) {
  const controller = useConsistencyPanelController(initialReportId);
  return <ConsistencyPanelLayout controller={controller} />;
}

function useConsistencyPanelController(initialReportId: string | null) {
  const queryClient = useQueryClient();
  // `null` = no explicit user pick yet; the effective id falls back to the
  // `initialReportId` prop and then the first report (derived below).
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [filters, setFilters] = useState<SampleFilters>({
    severity: "",
    decision: "unreviewed",
    sigCd: "",
    orderBy: "sample_rank",
    desc: false,
    page: 1
  });
  const [decisionForm, setDecisionForm] = useState<DecisionForm | null>(null);
  const [lastRun, setLastRun] = useState<LoadJobStatus | ConsistencySampleRecheckResponse | null>(null);

  const selectedCaseCode = useConsistencyAnalysisStore((state) => state.selectedCaseCode);
  const selectedSampleId = useConsistencyAnalysisStore((state) => state.selectedSampleId);
  const selectedSampleIds = useConsistencyAnalysisStore((state) => state.selectedSampleIds);
  const setSelectedCase = useConsistencyAnalysisStore((state) => state.setSelectedCase);
  const setSelectedSample = useConsistencyAnalysisStore((state) => state.setSelectedSample);
  const toggleSample = useConsistencyAnalysisStore((state) => state.toggleSample);
  const clearSelection = useConsistencyAnalysisStore((state) => state.clearSelection);

  const reportsQuery = useQuery({
    queryKey: ["consistency-reports"],
    queryFn: () => requestJson<ConsistencyReportSummary[]>("/admin/consistency")
  });
  const definitionsQuery = useQuery({
    queryKey: ["consistency-case-definitions"],
    queryFn: () => requestJson<ConsistencyCaseDefinition[]>("/admin/consistency/case-definitions")
  });
  const effectiveReportId =
    selectedReportId ?? initialReportId ?? reportsQuery.data?.[0]?.report_id ?? null;

  const reportQuery = useQuery({
    queryKey: ["consistency-report", effectiveReportId],
    queryFn: () => requestJson<ConsistencyReport>(`/admin/consistency/${effectiveReportId}`),
    enabled: effectiveReportId !== null
  });
  const reportCases = useMemo(() => reportQuery.data?.cases ?? EMPTY_CASES, [reportQuery.data?.cases]);
  const effectiveSelectedCaseCode = useMemo(() => {
    if (reportCases.some((item) => item.code === selectedCaseCode)) {
      return selectedCaseCode;
    }
    return reportCases[0]?.code ?? null;
  }, [reportCases, selectedCaseCode]);
  const samplesPath = useMemo(
    () =>
      effectiveReportId && effectiveSelectedCaseCode
        ? consistencySamplesPath({
            reportId: effectiveReportId,
            caseCode: effectiveSelectedCaseCode,
            severity: filters.severity || undefined,
            decision: filters.decision || undefined,
            sigCd: filters.sigCd || undefined,
            orderBy: filters.orderBy,
            desc: filters.desc,
            page: filters.page,
            pageSize: PAGE_SIZE
          })
        : null,
    [effectiveReportId, effectiveSelectedCaseCode, filters]
  );
  const samplesQuery = useQuery({
    queryKey: ["consistency-samples", samplesPath],
    queryFn: () => requestJson<ConsistencySamplePage>(samplesPath ?? ""),
    enabled: samplesPath !== null
  });
  const summaryQuery = useQuery({
    queryKey: ["consistency-summary", effectiveReportId, effectiveSelectedCaseCode],
    queryFn: () =>
      requestJson<ConsistencyCaseSummary>(
        `/admin/consistency/${effectiveReportId}/cases/${effectiveSelectedCaseCode}/summary`
      ),
    enabled: effectiveReportId !== null && effectiveSelectedCaseCode !== null
  });

  const definitionsByCode = useMemo(() => {
    return new Map((definitionsQuery.data ?? []).map((item) => [item.code, item]));
  }, [definitionsQuery.data]);

  const selectedCase = reportCases.find((item) => item.code === effectiveSelectedCaseCode);
  const selectedDefinition =
    effectiveSelectedCaseCode !== null ? definitionsByCode.get(effectiveSelectedCaseCode) : undefined;
  const samples = useMemo(() => samplesQuery.data?.items ?? EMPTY_SAMPLES, [samplesQuery.data]);
  const sampleIds = useMemo(() => new Set(samples.map((sample) => sample.sample_id)), [samples]);
  const effectiveSelectedSampleId =
    selectedSampleId !== null && sampleIds.has(selectedSampleId) ? selectedSampleId : null;
  const effectiveSelectedSampleIds = useMemo(
    () => selectedSampleIds.filter((sampleId) => sampleIds.has(sampleId)),
    [sampleIds, selectedSampleIds]
  );
  const selectedSample =
    effectiveSelectedSampleId !== null
      ? samples.find((sample) => sample.sample_id === effectiveSelectedSampleId) ?? null
      : null;

  const runMutation = useMutation({
    mutationFn: () => postJson<LoadJobStatus>("/admin/consistency/run", { scope: "full" }),
    onSuccess: (data) => {
      setLastRun(data);
      void queryClient.invalidateQueries({ queryKey: ["consistency-reports"] });
    }
  });

  const decisionMutation = useMutation({
    mutationFn: (form: DecisionForm) =>
      submitDecision(form, {
        reportId: effectiveReportId,
        caseCode: effectiveSelectedCaseCode,
        sampleId: effectiveSelectedSampleId,
        sampleIds: effectiveSelectedSampleIds
      }),
    onSuccess: () => {
      setDecisionForm(null);
      clearSelection();
      void queryClient.invalidateQueries({ queryKey: ["consistency-samples"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-report"] });
    }
  });

  const recheckMutation = useMutation({
    mutationFn: () => {
      if (!effectiveReportId || !effectiveSelectedCaseCode || !effectiveSelectedSampleId) {
        throw new Error("sample is not selected");
      }
      return postJson<ConsistencySampleRecheckResponse>(
        `/admin/consistency/${effectiveReportId}/cases/${effectiveSelectedCaseCode}/samples/${effectiveSelectedSampleId}/recheck`,
        {}
      );
    },
    onSuccess: (data) => {
      setLastRun(data);
      void queryClient.invalidateQueries({ queryKey: ["consistency-samples"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-summary"] });
    }
  });

  const columns = useSampleColumns({
    selectedSampleIds: effectiveSelectedSampleIds,
    selectedSampleId: effectiveSelectedSampleId,
    onToggle: toggleSample,
    onSelect: setSelectedSample
  });
  // TanStack Table exposes instance callbacks that React Compiler cannot memoize safely.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: samples,
    columns,
    getCoreRowModel: getCoreRowModel()
  });

  const csvHref =
    effectiveReportId !== null && effectiveSelectedCaseCode !== null
      ? `${API_BASE}${backendPath(
          consistencySamplesPath({
            reportId: effectiveReportId,
            caseCode: effectiveSelectedCaseCode,
            severity: filters.severity || undefined,
            decision: filters.decision || undefined,
            sigCd: filters.sigCd || undefined,
            orderBy: filters.orderBy,
            desc: filters.desc,
            page: filters.page,
            pageSize: PAGE_SIZE,
            format: "csv"
          })
        )}`
      : "#";

  return {
    clearSelection,
    csvHref,
    decisionForm,
    decisionPending: decisionMutation.isPending,
    effectiveReportId,
    effectiveSelectedCaseCode,
    effectiveSelectedSampleIds,
    filters,
    lastRun,
    onCloseDecision: () => setDecisionForm(null),
    onDecisionChange: (form: DecisionForm) => setDecisionForm(form),
    onDecisionSubmit: () => {
      if (decisionForm) {
        decisionMutation.mutate(decisionForm);
      }
    },
    onFiltersChange: (nextFilters: SampleFilters) => setFilters(nextFilters),
    onPage: (page: number) => setFilters((current) => ({ ...current, page })),
    onRefreshReports: () => reportsQuery.refetch(),
    onRecheck: () => recheckMutation.mutate(),
    onRun: () => runMutation.mutate(),
    onSelectCase: (caseCode: string) => {
      setSelectedCase(caseCode);
      setFilters((current) => ({ ...current, page: 1 }));
    },
    onSelectReport: (reportId: string) => setSelectedReportId(reportId),
    reportCases,
    reports: reportsQuery.data ?? [],
    reportTitle: reportQuery.data?.report_id ?? "Report",
    recheckDisabled:
      effectiveSelectedSampleId === null ||
      effectiveSelectedCaseCode === null ||
      recheckMutation.isPending,
    sampleCountForDecision:
      decisionForm?.target === "bulk" ? effectiveSelectedSampleIds.length : 1,
    selectedCase,
    selectedDefinition,
    selectedSample,
    summary: summaryQuery.data,
    table,
    totalSamples: samplesQuery.data?.total ?? 0
  };
}

type ConsistencyPanelController = ReturnType<typeof useConsistencyPanelController>;

function ConsistencyPanelLayout({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <div className="consistency-shell">
      <ReportsPanelSection controller={controller} />
      <ReportWorkbenchPanel controller={controller} />
      {controller.decisionForm ? (
        <DecisionModal
          form={controller.decisionForm}
          pending={controller.decisionPending}
          sampleCount={controller.sampleCountForDecision}
          onClose={controller.onCloseDecision}
          onChange={controller.onDecisionChange}
          onSubmit={controller.onDecisionSubmit}
        />
      ) : null}
      {controller.lastRun ? <LastActionPanel lastRun={controller.lastRun} /> : null}
    </div>
  );
}

function ReportsPanelSection({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <Panel
      title="Reports"
      actions={
        <div className="button-row">
          <button
            className="icon-button"
            onClick={() => void controller.onRefreshReports()}
            title="새로고침"
            type="button"
          >
            <RefreshCw size={16} />
          </button>
          <button className="button" onClick={controller.onRun} type="button">
            <Play size={16} />
            재검증
          </button>
        </div>
      }
    >
      <div className="report-list">
        {controller.reports.map((report) => (
          <DocumentNavLink
            className={report.report_id === controller.effectiveReportId ? "report-row active" : "report-row"}
            href={`/admin/consistency/${report.report_id}`}
            key={report.report_id}
          >
            <span>{report.report_id}</span>
            <StatusBadge value={report.severity_max} />
          </DocumentNavLink>
        ))}
      </div>
    </Panel>
  );
}

function ReportWorkbenchPanel({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <Panel title={controller.reportTitle}>
      <div className="consistency-workbench">
        <CaseTabs
          cases={controller.reportCases}
          onSelectCase={controller.onSelectCase}
          selectedCaseCode={controller.effectiveSelectedCaseCode}
        />
        <ConsistencyAnalysisSection controller={controller} />
      </div>
    </Panel>
  );
}

function CaseTabs({
  cases,
  onSelectCase,
  selectedCaseCode
}: {
  cases: ConsistencyReport["cases"];
  onSelectCase: (caseCode: string) => void;
  selectedCaseCode: string | null;
}) {
  return (
    <nav aria-label="정합성 케이스 선택" className="case-tabs">
      <div aria-label="정합성 케이스" aria-orientation="horizontal" className="case-tab-list" role="tablist">
        {cases.map((item) => {
          const isSelected = item.code === selectedCaseCode;
          return (
            <button
              aria-controls="consistency-case-panel"
              aria-selected={isSelected}
              className={isSelected ? "case-tab active" : "case-tab"}
              id={`case-tab-${item.code}`}
              key={item.code}
              onClick={() => onSelectCase(item.code)}
              role="tab"
              type="button"
            >
              <strong>{item.code}</strong>
              <span>{item.name}</span>
              <StatusBadge value={item.severity} />
              <small>{item.count.toLocaleString()}건</small>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function ConsistencyAnalysisSection({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <section
      aria-labelledby={`case-tab-${controller.effectiveSelectedCaseCode ?? "none"}`}
      className="analysis-pane"
      id="consistency-case-panel"
      role="tabpanel"
    >
      <CriteriaPanel
        caseCount={controller.selectedCase?.count ?? 0}
        definition={controller.selectedDefinition}
        summary={controller.summary}
      />
      <FilterToolbar filters={controller.filters} onChange={controller.onFiltersChange} />
      {controller.effectiveSelectedSampleIds.length > 0 ? (
        <BulkBar
          count={controller.effectiveSelectedSampleIds.length}
          onClear={controller.clearSelection}
          onOpen={(state) => controller.onDecisionChange(openDecisionForm("bulk", state))}
        />
      ) : null}
      <div className="comparison-grid">
        <div className="table-pane">
          <table className="table compact consistency-table">
            <thead>
              {controller.table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {controller.table.getRowModel().rows.map((row) => (
                <tr
                  className={row.original.sample_id === (controller.selectedSample?.sample_id ?? null) ? "active-row" : ""}
                  key={row.id}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            onPage={controller.onPage}
            page={controller.filters.page}
            pageSize={PAGE_SIZE}
            total={controller.totalSamples}
          />
        </div>

        <div className="detail-pane">
          <DecisionPanel
            onAction={(state) => controller.onDecisionChange(openDecisionForm("single", state))}
            onRecheck={controller.onRecheck}
            recheckDisabled={controller.recheckDisabled}
            sample={controller.selectedSample}
          />
          <a className="button secondary" href={controller.csvHref}>
            <Download size={16} />
            CSV 내려받기
          </a>
        </div>
      </div>

      <section className="map-section">
        <h3 className="map-section-title">선택한 표본 위치</h3>
        <MapPreview sample={controller.selectedSample} />
      </section>
    </section>
  );
}

function LastActionPanel({
  lastRun
}: {
  lastRun: LoadJobStatus | ConsistencySampleRecheckResponse;
}) {
  return (
    <Panel title="Last Action">
      <pre className="json-box">{JSON.stringify(lastRun, null, 2)}</pre>
    </Panel>
  );
}

function useSampleColumns({
  selectedSampleIds,
  selectedSampleId,
  onToggle,
  onSelect
}: {
  selectedSampleIds: string[];
  selectedSampleId: string | null;
  onToggle: (sampleId: string) => void;
  onSelect: (sampleId: string | null) => void;
}): ColumnDef<ConsistencyCaseSample>[] {
  return useMemo(
    () => [
      {
        id: "select",
        header: "",
        cell: ({ row }) => (
          <input
            aria-label={`표본 #${row.original.sample_rank + 1} 선택`}
            checked={selectedSampleIds.includes(row.original.sample_id)}
            onChange={() => onToggle(row.original.sample_id)}
            type="checkbox"
          />
        )
      },
      {
        header: "표본",
        accessorKey: "sample_rank",
        cell: ({ row }) => (
          <button
            className={row.original.sample_id === selectedSampleId ? "link-button active" : "link-button"}
            onClick={() => onSelect(row.original.sample_id)}
            type="button"
          >
            #{row.original.sample_rank + 1}
          </button>
        )
      },
      {
        header: "심각도",
        accessorKey: "severity",
        cell: ({ row }) => <StatusBadge value={row.original.severity} />
      },
      {
        header: "판정",
        accessorKey: "decision_state",
        cell: ({ row }) => <DecisionBadge value={row.original.decision_state} />
      },
      { header: "건물관리번호", accessorKey: "bd_mgt_sn" },
      { header: "시군구코드", accessorKey: "sig_cd" },
      {
        header: "거리",
        accessorKey: "distance_m",
        cell: ({ row }) =>
          row.original.distance_m === null || row.original.distance_m === undefined
            ? "-"
            : `${row.original.distance_m.toFixed(2)}m`
      },
      { header: "원천", accessorKey: "source_kind" },
      { header: "사유", accessorKey: "reason_code" }
    ],
    [onSelect, onToggle, selectedSampleId, selectedSampleIds]
  );
}

function CriteriaPanel({
  definition,
  caseCount,
  summary
}: {
  definition: ConsistencyCaseDefinition | undefined;
  caseCount: number;
  summary: ConsistencyCaseSummary | undefined;
}) {
  if (!definition) return null;
  return (
    <div className="criteria-panel">
      <div>
        <h3>
          {definition.code} {definition.name}
        </h3>
        <p>{definition.compares}</p>
      </div>
      <dl className="criteria-grid">
        <div>
          <dt>비정상 기준</dt>
          <dd>{definition.abnormal_criteria}</dd>
        </div>
        <div>
          <dt>판정 가이드</dt>
          <dd>{definition.decision_guide}</dd>
        </div>
        <div>
          <dt>증거</dt>
          <dd>{definition.evidence.join(", ")}</dd>
        </div>
        <div>
          <dt>진행률</dt>
          <dd>
            {Object.entries(summary?.by_decision ?? {})
              .map(([key, value]) => `${decisionLabels[key as ConsistencyDecisionState] ?? key} ${value}`)
              .join(" · ") || `${caseCount.toLocaleString()}건`}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function FilterToolbar({
  filters,
  onChange
}: {
  filters: SampleFilters;
  onChange: (filters: SampleFilters) => void;
}) {
  return (
    <div className="filter-bar">
      <select
        aria-label="심각도 필터"
        onChange={(event) => onChange({ ...filters, severity: event.target.value, page: 1 })}
        value={filters.severity}
      >
        <option value="">심각도 전체</option>
        <option value="ERROR">오류 (ERROR)</option>
        <option value="WARN">경고 (WARN)</option>
        <option value="INFO">정보 (INFO)</option>
        <option value="OK">정상 (OK)</option>
      </select>
      <select
        aria-label="판정 필터"
        onChange={(event) => onChange({ ...filters, decision: event.target.value, page: 1 })}
        value={filters.decision}
      >
        <option value="">판정 전체</option>
        <option value="unreviewed">미검토</option>
        <option value="approved">승인</option>
        <option value="rejected">거절</option>
        <option value="deferred">보류</option>
      </select>
      <input
        aria-label="시군구코드 필터"
        maxLength={5}
        onChange={(event) => onChange({ ...filters, sigCd: event.target.value, page: 1 })}
        placeholder="시군구코드 (예: 41465)"
        value={filters.sigCd}
      />
      <select
        aria-label="정렬 기준"
        onChange={(event) => onChange({ ...filters, orderBy: event.target.value, page: 1 })}
        value={filters.orderBy}
      >
        <option value="sample_rank">정렬: 표본 순서</option>
        <option value="distance_m">정렬: 거리</option>
        <option value="severity">정렬: 심각도</option>
        <option value="reviewed_at">정렬: 검토 시각</option>
      </select>
      <label className="checkbox-row">
        <input
          checked={filters.desc}
          onChange={(event) => onChange({ ...filters, desc: event.target.checked, page: 1 })}
          type="checkbox"
        />
        내림차순
      </label>
    </div>
  );
}

function BulkBar({
  count,
  onClear,
  onOpen
}: {
  count: number;
  onClear: () => void;
  onOpen: (state: ActionState) => void;
}) {
  return (
    <div className="bulk-bar">
      <strong>{count.toLocaleString()}개 선택</strong>
      <button className="button secondary" onClick={() => onOpen("approved")} type="button">
        <Check size={16} />
        승인
      </button>
      <button className="button secondary" onClick={() => onOpen("deferred")} type="button">
        <Clock size={16} />
        보류
      </button>
      <button className="button danger" onClick={() => onOpen("rejected")} type="button">
        <X size={16} />
        거절
      </button>
      <button className="button secondary" onClick={onClear} type="button">
        선택 해제
      </button>
    </div>
  );
}

function MapPreview({ sample }: { sample: ConsistencyCaseSample | null }) {
  if (!sample) {
    return (
      <div className="map-preview">
        <div className="map-box map-placeholder">
          <div className="map-marker">
            <strong>표본 선택 대기</strong>
            <span>위 표에서 표본을 선택하면 지도와 증거를 표시합니다</span>
          </div>
        </div>
      </div>
    );
  }

  const point = sample.point ?? null;
  return (
    <div className="map-preview">
      {point ? (
        <LazyCoordinateMap point={point} />
      ) : (
        <div className="map-box map-placeholder">
          <div className="map-marker">
            <strong>좌표 없음</strong>
            <span>이 표본에는 표시할 좌표가 없습니다 (증거는 아래 상세에서 확인)</span>
          </div>
        </div>
      )}
      <div className="map-legend">
        <span>분류 {sample.case_code}</span>
        <span>{sample.distance_m ? `거리 ${sample.distance_m.toFixed(2)}m` : "거리 정보 없음"}</span>
        <span>{sample.has_polygon ? "건물 도형 있음" : "건물 도형 없음"}</span>
        <span>{sample.has_line ? "도로선 있음" : "도로선 없음"}</span>
      </div>
    </div>
  );
}

function DecisionPanel({
  sample,
  recheckDisabled,
  onAction,
  onRecheck
}: {
  sample: ConsistencyCaseSample | null;
  recheckDisabled: boolean;
  onAction: (state: ActionState) => void;
  onRecheck: () => void;
}) {
  return (
    <div className="decision-panel">
      <div>
        <strong>{sample ? `#${sample.sample_rank + 1}` : "sample 없음"}</strong>
        <DecisionBadge value={sample?.decision_state ?? "unreviewed"} />
      </div>
      <div className="button-row">
        <button className="button secondary" disabled={!sample} onClick={() => onAction("approved")} type="button">
          <Check size={16} />
          승인
        </button>
        <button className="button secondary" disabled={!sample} onClick={() => onAction("deferred")} type="button">
          <Clock size={16} />
          보류
        </button>
        <button className="button danger" disabled={!sample} onClick={() => onAction("rejected")} type="button">
          <X size={16} />
          거절
        </button>
        <button className="icon-button" disabled={recheckDisabled} onClick={onRecheck} title="재검증" type="button">
          <RotateCw size={16} />
        </button>
      </div>
      {sample ? <pre className="json-box compact-json">{JSON.stringify(sample.source_snapshot, null, 2)}</pre> : null}
    </div>
  );
}

function DecisionModal({
  form,
  pending,
  sampleCount,
  onChange,
  onClose,
  onSubmit
}: {
  form: DecisionForm;
  pending: boolean;
  sampleCount: number;
  onChange: (form: DecisionForm) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const reasons = decisionReasons[form.state];
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h2>
          {decisionLabels[form.state]} · {sampleCount.toLocaleString()}건
        </h2>
        <div className="form-grid">
          <label className="field">
            <span>reason</span>
            <select
              onChange={(event) => onChange({ ...form, reasonCode: event.target.value })}
              value={form.reasonCode}
            >
              {reasons.map((reason) => (
                <option key={reason} value={reason}>
                  {reason}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>reviewer</span>
            <input
              onChange={(event) => onChange({ ...form, reviewer: event.target.value })}
              value={form.reviewer}
            />
          </label>
          <label className="field">
            <span>note</span>
            <textarea
              onChange={(event) => onChange({ ...form, note: event.target.value })}
              value={form.note}
            />
          </label>
        </div>
        <div className="button-row">
          <button className="button" disabled={pending || !form.reasonCode} onClick={onSubmit} type="button">
            저장
          </button>
          <button className="button secondary" disabled={pending} onClick={onClose} type="button">
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

function DecisionBadge({ value }: { value: ConsistencyDecisionState }) {
  return <span className={`decision-badge ${value}`}>{decisionLabels[value]}</span>;
}

function Pager({
  page,
  pageSize,
  total,
  onPage
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <button className="button secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} type="button">
        이전
      </button>
      <span>
        {page.toLocaleString()} / {totalPages.toLocaleString()} · {total.toLocaleString()}건
      </span>
      <button
        className="button secondary"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        type="button"
      >
        다음
      </button>
    </div>
  );
}

function openDecisionForm(target: DecisionTarget, state: ActionState): DecisionForm {
  return {
    target,
    state,
    reasonCode: decisionReasons[state][0],
    reviewer: "ui",
    note: ""
  };
}

async function submitDecision(
  form: DecisionForm,
  target: {
    reportId: string | null;
    caseCode: string | null;
    sampleId: string | null;
    sampleIds: string[];
  }
) {
  if (!target.reportId) throw new Error("report is not selected");
  if (!target.caseCode) throw new Error("case is not selected");
  const base = `/admin/consistency/${target.reportId}/cases/${target.caseCode}/samples`;
  const payload: ConsistencySampleDecisionRequest = {
    decision_state: form.state,
    reason_code: form.reasonCode,
    note: form.note || null,
    reviewer: form.reviewer || "ui"
  };
  if (form.target === "bulk") {
    const bulkPayload: ConsistencyBulkDecisionRequest = {
      ...payload,
      sample_ids: target.sampleIds
    };
    return postJson(`${base}/bulk-decision`, bulkPayload);
  }
  if (!target.sampleId) throw new Error("sample is not selected");
  return patchJson(`${base}/${target.sampleId}/decision`, payload);
}
