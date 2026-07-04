"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Clock, Download, Play, RotateCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminTabs, AdminTabsContent } from "@/components/admin/shared/AdminTabs";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { ConfirmActionDialog } from "@/components/admin/shared/ConfirmActionDialog";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { JsonDetails } from "@/components/admin/shared/JsonDetails";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { LazyCoordinateMap } from "@/components/vworld/LazyCoordinateMap";
import {
  API_BASE,
  backendPath,
  getErrorMessage,
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
  decisionReasonLabel,
  decisionReasons
} from "@/lib/consistency";
import { useConsistencyAnalysisStore } from "@/lib/stores/consistency-analysis-store";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

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
const SIG_CD_DEBOUNCE_MS = 300;
const REVIEWER_STORAGE_KEY = "kortravelgeo.consistencyReviewer";

// Stable empty reference so `samples` doesn't get a brand-new array on every render
// while the samples query is loading. Passing a fresh `[]` into useReactTable on each
// render makes TanStack Table's auto-reset fire a state update every render, which spins
// React into an infinite re-render loop that pins the main thread and freezes the tab
// (notably when switching cases C1~C10, whose refetch leaves the data briefly undefined).
const EMPTY_SAMPLES: ConsistencyCaseSample[] = [];
const EMPTY_CASES: ConsistencyReport["cases"] = [];
const EMPTY_REPORTS: ConsistencyReportSummary[] = [];
const EMPTY_DEFINITIONS: ConsistencyCaseDefinition[] = [];

function loadStoredReviewer(): string {
  if (typeof window === "undefined") return "ui";
  try {
    return window.localStorage.getItem(REVIEWER_STORAGE_KEY)?.trim() || "ui";
  } catch {
    return "ui";
  }
}

function storeReviewer(reviewer: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(REVIEWER_STORAGE_KEY, reviewer);
  } catch {
    // 저장 실패는 무시 — 다음 판정에서 기본값 "ui"로 돌아간다.
  }
}

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

  const { data: reports = EMPTY_REPORTS, refetch: refetchReports } = useQuery({
    queryKey: ["consistency-reports"],
    queryFn: () => requestJson<ConsistencyReportSummary[]>("/admin/consistency")
  });
  const { data: definitions = EMPTY_DEFINITIONS } = useQuery({
    queryKey: ["consistency-case-definitions"],
    queryFn: () => requestJson<ConsistencyCaseDefinition[]>("/admin/consistency/case-definitions")
  });
  const effectiveReportId =
    selectedReportId ?? initialReportId ?? reports[0]?.report_id ?? null;

  const { data: report } = useQuery({
    queryKey: ["consistency-report", effectiveReportId],
    queryFn: () => requestJson<ConsistencyReport>(`/admin/consistency/${effectiveReportId}`),
    enabled: effectiveReportId !== null
  });
  const reportCases = useMemo(() => report?.cases ?? EMPTY_CASES, [report?.cases]);
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
  const { data: samplePage } = useQuery({
    queryKey: ["consistency-samples", samplesPath],
    queryFn: () => requestJson<ConsistencySamplePage>(samplesPath ?? ""),
    enabled: samplesPath !== null
  });
  const { data: summary } = useQuery({
    queryKey: ["consistency-summary", effectiveReportId, effectiveSelectedCaseCode],
    queryFn: () =>
      requestJson<ConsistencyCaseSummary>(
        `/admin/consistency/${effectiveReportId}/cases/${effectiveSelectedCaseCode}/summary`
      ),
    enabled: effectiveReportId !== null && effectiveSelectedCaseCode !== null
  });

  const definitionsByCode = useMemo(() => {
    return new Map(definitions.map((item) => [item.code, item]));
  }, [definitions]);

  const selectedCase = reportCases.find((item) => item.code === effectiveSelectedCaseCode);
  const selectedDefinition =
    effectiveSelectedCaseCode !== null ? definitionsByCode.get(effectiveSelectedCaseCode) : undefined;
  const samples = useMemo(() => samplePage?.items ?? EMPTY_SAMPLES, [samplePage?.items]);
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
      toast.success("전체 검증을 시작했습니다.");
      void queryClient.invalidateQueries({ queryKey: ["consistency-reports"] });
    },
    onError: (error) => {
      toast.error("전체 검증 실행 실패", getErrorMessage(error));
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
    onSuccess: (_data, form) => {
      storeReviewer(form.reviewer.trim() || "ui");
      setDecisionForm(null);
      clearSelection();
      toast.success("판정을 저장했습니다.");
      void queryClient.invalidateQueries({ queryKey: ["consistency-samples"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-report"] });
    },
    onError: (error) => {
      toast.error("판정 저장 실패", getErrorMessage(error));
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
      toast.success("표본을 다시 확인했습니다.");
      void queryClient.invalidateQueries({ queryKey: ["consistency-samples"] });
      void queryClient.invalidateQueries({ queryKey: ["consistency-summary"] });
    },
    onError: (error) => {
      toast.error("표본 재확인 실패", getErrorMessage(error));
    }
  });

  const allOnPageSelected =
    samples.length > 0 && effectiveSelectedSampleIds.length === samples.length;
  const onToggleAllOnPage = useCallback(() => {
    const selected = new Set(selectedSampleIds);
    for (const sample of samples) {
      const isSelected = selected.has(sample.sample_id);
      if (allOnPageSelected ? isSelected : !isSelected) {
        toggleSample(sample.sample_id);
      }
    }
  }, [allOnPageSelected, samples, selectedSampleIds, toggleSample]);

  const sampleColumns = useSampleColumns({
    allSelected: allOnPageSelected,
    onToggleAll: onToggleAllOnPage,
    selectedSampleIds: effectiveSelectedSampleIds,
    selectedSampleId: effectiveSelectedSampleId,
    onToggle: toggleSample,
    onSelect: setSelectedSample
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
      : null;

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
    onRefreshReports: () => refetchReports(),
    onRecheck: () => recheckMutation.mutate(),
    onRun: () => runMutation.mutate(),
    onSelectCase: (caseCode: string) => {
      setSelectedCase(caseCode);
      setFilters((current) => ({ ...current, page: 1 }));
    },
    onSelectReport: (reportId: string) => setSelectedReportId(reportId),
    reportCases,
    reports,
    reportTitle: report?.report_id ?? "Report",
    recheckDisabled:
      effectiveSelectedSampleId === null ||
      effectiveSelectedCaseCode === null ||
      recheckMutation.isPending,
    sampleCountForDecision:
      decisionForm?.target === "bulk" ? effectiveSelectedSampleIds.length : 1,
    sampleColumns,
    samples,
    selectedCase,
    selectedDefinition,
    selectedSample,
    // 다른 페이지/필터에서 선택했던 표본 수 — 현재 페이지 밖이라 일괄 판정에서 제외된다.
    staleSelectedCount: selectedSampleIds.length - effectiveSelectedSampleIds.length,
    summary,
    totalSamples: samplePage?.total ?? 0
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
      <ActionResultPanel result={controller.lastRun} />
    </div>
  );
}

function ReportsPanelSection({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <Panel
      title="Reports"
      actions={
        <>
          <RefreshButton iconOnly onClick={() => void controller.onRefreshReports()} />
          <ConfirmActionDialog
            confirmLabel="전체 검증 실행"
            description="전체 검증을 다시 실행합니다. 새 정합성 리포트가 생성되며 데이터 양에 따라 시간이 걸릴 수 있습니다."
            destructive={false}
            onConfirm={controller.onRun}
            title="전체 검증 실행"
            trigger={
              <Button size="sm" type="button">
                <Play aria-hidden="true" />
                전체 검증 실행
              </Button>
            }
          />
        </>
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
  const caseValue = controller.effectiveSelectedCaseCode ?? "";
  return (
    <Panel title={controller.reportTitle}>
      <div className="consistency-workbench">
        <AdminTabs
          className="case-tabs"
          items={controller.reportCases.map((item) => ({
            value: item.code,
            label: (
              <>
                <strong>{item.code}</strong>
                <span className="max-w-44 truncate">{item.name}</span>
                <StatusBadge value={item.severity} />
                <small>{item.count.toLocaleString()}건</small>
              </>
            )
          }))}
          label="정합성 케이스"
          onValueChange={controller.onSelectCase}
          value={caseValue}
        >
          <AdminTabsContent className="analysis-pane" value={caseValue}>
            <ConsistencyAnalysisSection controller={controller} />
          </AdminTabsContent>
        </AdminTabs>
      </div>
    </Panel>
  );
}

function ConsistencyAnalysisSection({ controller }: { controller: ConsistencyPanelController }) {
  return (
    <>
      <CriteriaPanel
        caseCount={controller.selectedCase?.count ?? 0}
        definition={controller.selectedDefinition}
        summary={controller.summary}
      />
      <FilterToolbar
        filters={controller.filters}
        onChange={controller.onFiltersChange}
        summary={controller.summary}
      />
      {controller.effectiveSelectedSampleIds.length > 0 ? (
        <BulkBar
          count={controller.effectiveSelectedSampleIds.length}
          onClear={controller.clearSelection}
          onOpen={(state) => controller.onDecisionChange(openDecisionForm("bulk", state))}
        />
      ) : null}
      {controller.staleSelectedCount > 0 ? (
        <p className="m-0 text-xs text-muted-foreground" role="status">
          다른 페이지에서 선택한 {controller.staleSelectedCount.toLocaleString()}건은 현재 일괄
          판정에서 제외됩니다.
        </p>
      ) : null}
      <div className="comparison-grid">
        <div className="table-pane">
          <VirtualTable
            as="table"
            columns={controller.sampleColumns}
            compact
            emptyHint="표본이 없습니다."
            getRowClassName={(sample) =>
              sample.sample_id === (controller.selectedSample?.sample_id ?? null)
                ? "active-row"
                : undefined
            }
            rowKey={(sample) => sample.sample_id}
            rows={controller.samples}
          />
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
          <div className="flex items-center gap-1">
            {controller.csvHref ? (
              <Button asChild size="sm" variant="outline">
                <a href={controller.csvHref}>
                  <Download aria-hidden="true" />
                  CSV 내려받기
                </a>
              </Button>
            ) : (
              <Button aria-disabled="true" disabled size="sm" type="button" variant="outline">
                <Download aria-hidden="true" />
                CSV 내려받기
              </Button>
            )}
            <HelpTip label="CSV 내려받기 도움말">
              현재 필터와 페이지 기준의 표본(최대 {PAGE_SIZE}건)을 CSV로 내려받습니다.
            </HelpTip>
          </div>
        </div>
      </div>

      <section className="map-section">
        <h3 className="map-section-title">선택한 표본 위치</h3>
        <MapPreview sample={controller.selectedSample} />
      </section>
    </>
  );
}

function useSampleColumns({
  allSelected,
  onToggleAll,
  selectedSampleIds,
  selectedSampleId,
  onToggle,
  onSelect
}: {
  allSelected: boolean;
  onToggleAll: () => void;
  selectedSampleIds: string[];
  selectedSampleId: string | null;
  onToggle: (sampleId: string) => void;
  onSelect: (sampleId: string | null) => void;
}): VirtualColumn<ConsistencyCaseSample>[] {
  return useMemo(
    () => [
      {
        key: "select",
        header: "",
        headerCell: (
          <Checkbox aria-label="전체 선택" checked={allSelected} onCheckedChange={onToggleAll} />
        ),
        cell: (sample) => (
          <Checkbox
            aria-label={`표본 #${sample.sample_rank + 1} 선택`}
            checked={selectedSampleIds.includes(sample.sample_id)}
            onCheckedChange={() => onToggle(sample.sample_id)}
          />
        )
      },
      {
        key: "sample_rank",
        header: "표본",
        cell: (sample) => (
          <Button
            className={cn(
              "link-button min-h-0 min-w-0 px-0",
              sample.sample_id === selectedSampleId && "active"
            )}
            onClick={() => onSelect(sample.sample_id)}
            size="xs"
            type="button"
            variant="link"
          >
            #{sample.sample_rank + 1}
          </Button>
        )
      },
      {
        key: "severity",
        header: "심각도",
        cell: (sample) => <StatusBadge value={sample.severity} />
      },
      {
        key: "decision_state",
        header: "판정",
        cell: (sample) => <DecisionBadge value={sample.decision_state} />
      },
      { key: "bd_mgt_sn", header: "건물관리번호", cell: (sample) => sample.bd_mgt_sn },
      { key: "sig_cd", header: "시군구코드", cell: (sample) => sample.sig_cd },
      {
        key: "distance_m",
        header: "거리",
        cell: (sample) =>
          sample.distance_m === null || sample.distance_m === undefined
            ? "-"
            : `${sample.distance_m.toFixed(2)}m`
      },
      { key: "source_kind", header: "원천", cell: (sample) => sample.source_kind },
      { key: "reason_code", header: "사유", cell: (sample) => sample.reason_code }
    ],
    [allSelected, onSelect, onToggle, onToggleAll, selectedSampleId, selectedSampleIds]
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
  const [criteriaOpen, setCriteriaOpen] = useState(false);
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
          <dt>진행률</dt>
          <dd>
            {Object.entries(summary?.by_decision ?? {})
              .map(([key, value]) => `${decisionLabels[key as ConsistencyDecisionState] ?? key} ${value}`)
              .join(" · ") || `${caseCount.toLocaleString()}건`}
          </dd>
        </div>
      </dl>
      <Collapsible className="grid justify-items-start gap-2" onOpenChange={setCriteriaOpen} open={criteriaOpen}>
        <CollapsibleTrigger className="inline-flex min-h-9 items-center gap-1 rounded-md px-1.5 text-xs font-semibold text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
          <ChevronDown
            aria-hidden="true"
            className={cn(
              "size-3.5 transition-transform duration-[var(--duration-fast)]",
              !criteriaOpen && "-rotate-90"
            )}
          />
          판정 기준 보기
        </CollapsibleTrigger>
        <CollapsibleContent className="grid w-full gap-3">
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
              <dt>추정 원인</dt>
              <dd>{definition.likely_causes.length > 0 ? definition.likely_causes.join(", ") : "-"}</dd>
            </div>
            <div>
              <dt>기본 심각도</dt>
              <dd>{definition.default_severity ? <StatusBadge value={definition.default_severity} /> : "-"}</dd>
            </div>
          </dl>
          {definition.sample_schema && Object.keys(definition.sample_schema).length > 0 ? (
            <JsonDetails summary="표본 구조" value={definition.sample_schema} />
          ) : null}
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function FilterToolbar({
  filters,
  summary,
  onChange
}: {
  filters: SampleFilters;
  summary: ConsistencyCaseSummary | undefined;
  onChange: (filters: SampleFilters) => void;
}) {
  // 시군구코드는 타이핑마다 refetch하지 않도록 300ms debounce 후 filters에 반영한다.
  const [sigCdDraft, setSigCdDraft] = useState(filters.sigCd);
  useEffect(() => {
    setSigCdDraft(filters.sigCd);
  }, [filters.sigCd]);
  useEffect(() => {
    if (sigCdDraft === filters.sigCd) return undefined;
    const timer = setTimeout(
      () => onChange({ ...filters, sigCd: sigCdDraft, page: 1 }),
      SIG_CD_DEBOUNCE_MS
    );
    return () => clearTimeout(timer);
  }, [filters, onChange, sigCdDraft]);

  const sigCdOptions = Object.keys(summary?.by_sig_cd ?? {});
  return (
    <div className="filter-bar">
      <div className="w-40">
        <NativeSelect
          aria-label="심각도 필터"
          onChange={(event) => onChange({ ...filters, severity: event.target.value, page: 1 })}
          value={filters.severity}
        >
          <option value="">심각도 전체</option>
          <option value="ERROR">오류 (ERROR)</option>
          <option value="WARN">경고 (WARN)</option>
          <option value="INFO">정보 (INFO)</option>
          <option value="OK">정상 (OK)</option>
        </NativeSelect>
      </div>
      <div className="w-40">
        <NativeSelect
          aria-label="판정 필터"
          onChange={(event) => onChange({ ...filters, decision: event.target.value, page: 1 })}
          value={filters.decision}
        >
          <option value="">판정 전체</option>
          <option value="unreviewed">미검토</option>
          <option value="approved">승인</option>
          <option value="rejected">거절</option>
          <option value="deferred">보류</option>
        </NativeSelect>
      </div>
      <div className="w-44">
        <Input
          aria-label="시군구코드 필터"
          inputMode="numeric"
          list={sigCdOptions.length > 0 ? "consistency-sig-cd-options" : undefined}
          maxLength={5}
          onChange={(event) => setSigCdDraft(event.target.value)}
          placeholder="시군구코드 (예: 41465)"
          value={sigCdDraft}
        />
        {sigCdOptions.length > 0 ? (
          <datalist id="consistency-sig-cd-options">
            {sigCdOptions.map((code) => (
              <option key={code} value={code} />
            ))}
          </datalist>
        ) : null}
      </div>
      <div className="w-44">
        <NativeSelect
          aria-label="정렬 기준"
          onChange={(event) => onChange({ ...filters, orderBy: event.target.value, page: 1 })}
          value={filters.orderBy}
        >
          <option value="sample_rank">정렬: 표본 순서</option>
          <option value="distance_m">정렬: 거리</option>
          <option value="severity">정렬: 심각도</option>
          <option value="reviewed_at">정렬: 검토 시각</option>
        </NativeSelect>
      </div>
      <label className="checkbox-row">
        <Checkbox
          checked={filters.desc}
          onCheckedChange={(checked) =>
            onChange({ ...filters, desc: checked === true, page: 1 })
          }
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
      <Button onClick={() => onOpen("approved")} size="sm" type="button" variant="outline">
        <Check aria-hidden="true" />
        승인
      </Button>
      <Button onClick={() => onOpen("deferred")} size="sm" type="button" variant="outline">
        <Clock aria-hidden="true" />
        보류
      </Button>
      <Button onClick={() => onOpen("rejected")} size="sm" type="button" variant="destructive">
        <X aria-hidden="true" />
        거절
      </Button>
      <Button onClick={onClear} size="sm" type="button" variant="ghost">
        선택 해제
      </Button>
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
            <span>이 표본에는 표시할 좌표가 없습니다.</span>
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
        <Button disabled={!sample} onClick={() => onAction("approved")} size="sm" type="button" variant="outline">
          <Check aria-hidden="true" />
          승인
        </Button>
        <Button disabled={!sample} onClick={() => onAction("deferred")} size="sm" type="button" variant="outline">
          <Clock aria-hidden="true" />
          보류
        </Button>
        <Button disabled={!sample} onClick={() => onAction("rejected")} size="sm" type="button" variant="destructive">
          <X aria-hidden="true" />
          거절
        </Button>
        <Button
          aria-label="이 표본 다시 확인"
          disabled={recheckDisabled}
          onClick={onRecheck}
          size="icon-sm"
          type="button"
          variant="outline"
        >
          <RotateCw aria-hidden="true" />
        </Button>
      </div>
      {sample?.case_metric && Object.keys(sample.case_metric).length > 0 ? (
        <div className="case-metric">
          <strong className="flex items-center gap-1">
            지표
            <HelpTip label="지표 도움말">
              표본별 케이스 지표 원본 필드 <code>case_metric</code> 값입니다.
            </HelpTip>
          </strong>
          <dl className="criteria-grid case-metric-grid">
            {Object.entries(sample.case_metric).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{formatMetricValue(value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
      {sample ? <JsonDetails summary="원천 스냅샷" value={sample.source_snapshot} /> : null}
    </div>
  );
}

function formatMetricValue(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
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
    <Dialog
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      open
    >
      <DialogContent
        onOpenAutoFocus={(event) => {
          // 접근성 계약 (T-227): 열리면 포커스가 reason select로 이동한다.
          event.preventDefault();
          document.getElementById("consistency-decision-reason")?.focus();
        }}
        showCloseButton={false}
      >
        <DialogHeader>
          <DialogTitle>정합성 판정</DialogTitle>
          <DialogDescription>
            {decisionLabels[form.state]} · {sampleCount.toLocaleString()}건
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <Field>
            <FieldLabel htmlFor="consistency-decision-reason">판정 사유</FieldLabel>
            <NativeSelect
              id="consistency-decision-reason"
              onChange={(event) => onChange({ ...form, reasonCode: event.target.value })}
              value={form.reasonCode}
            >
              {reasons.map((reason) => (
                <option key={reason} value={reason}>
                  {decisionReasonLabel(reason)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field>
            <FieldLabel htmlFor="consistency-decision-reviewer">검토자</FieldLabel>
            <Input
              id="consistency-decision-reviewer"
              onChange={(event) => onChange({ ...form, reviewer: event.target.value })}
              value={form.reviewer}
            />
            <FieldDescription>
              마지막 입력값을 기억합니다. 비우면 &quot;ui&quot;로 기록됩니다.
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="consistency-decision-note">메모 (선택)</FieldLabel>
            <textarea
              className="min-h-20 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              id="consistency-decision-note"
              onChange={(event) => onChange({ ...form, note: event.target.value })}
              placeholder="예: 지도 확인 결과 도로 반대편 좌표"
              value={form.note}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button disabled={pending || !form.reasonCode} onClick={onSubmit} type="button">
            저장
          </Button>
          <Button disabled={pending} onClick={onClose} type="button" variant="outline">
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const decisionTones = {
  approved: "ok",
  rejected: "error",
  deferred: "warn",
  unreviewed: "neutral"
} as const;

function DecisionBadge({ value }: { value: ConsistencyDecisionState }) {
  return (
    <Badge className={`decision-badge ${value}`} tone={decisionTones[value] ?? "neutral"}>
      {decisionLabels[value]}
    </Badge>
  );
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
      <Button disabled={page <= 1} onClick={() => onPage(page - 1)} size="sm" type="button" variant="outline">
        이전
      </Button>
      <span>
        {page.toLocaleString()} / {totalPages.toLocaleString()} · {total.toLocaleString()}건
      </span>
      <Button
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
        size="sm"
        type="button"
        variant="outline"
      >
        다음
      </Button>
    </div>
  );
}

function openDecisionForm(target: DecisionTarget, state: ActionState): DecisionForm {
  return {
    target,
    state,
    reasonCode: decisionReasons[state][0],
    reviewer: loadStoredReviewer(),
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
