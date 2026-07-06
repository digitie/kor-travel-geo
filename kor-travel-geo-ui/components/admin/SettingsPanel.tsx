"use client";

import { Copy, Eye, EyeOff, KeyRound, RotateCcw, Save, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ConfirmActionDialog } from "@/components/admin/shared/ConfirmActionDialog";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { NumberField } from "@/components/admin/shared/NumberField";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AuditEvent,
  RustfsConnectionCheck,
  RustfsStorageConfig,
  RustfsStorageConfigPatch,
  PublicApiKeyCreateResponse,
  PublicApiKeySummary,
  clearPublicApiKeyForRequestsByHint,
  deleteJson,
  getErrorMessage,
  patchJson,
  postJson,
  requestJson,
  savePublicApiKeyForRequests
} from "@/lib/api";
import { httpUrlSchema, s3BucketSchema } from "@/lib/schemas";
import { toast } from "@/lib/toast";
import { useVWorldApiKey } from "@/lib/vworld-key";

const sourceLabels = {
  browser: "브라우저 저장값",
  empty: "미설정",
  env: ".env 기본값",
  loading: "확인 중"
};

/** 섹션 공용 결과 알림 (성공/안내는 status, 오류는 alert로 살아있는 영역). */
type SectionNotice = {
  tone: "success" | "info" | "error";
  text: string;
};

function NoticeAlert({ notice }: { notice: SectionNotice }) {
  return (
    <Alert
      role={notice.tone === "error" ? "alert" : "status"}
      variant={
        notice.tone === "error" ? "destructive" : notice.tone === "success" ? "success" : "info"
      }
    >
      <AlertDescription>{notice.text}</AlertDescription>
    </Alert>
  );
}

export function SettingsPanel() {
  const { apiKey, envApiKey, loading, resetApiKey, saveApiKey, source } = useVWorldApiKey();
  const [rustfsConfig, setRustfsConfig] = useState<RustfsStorageConfig | null>(null);
  const [rustfsDraft, setRustfsDraft] = useState<RustfsDraft | null>(null);
  const [rustfsBusy, setRustfsBusy] = useState(false);
  const [rustfsLoadError, setRustfsLoadError] = useState<string | null>(null);
  const [rustfsNotice, setRustfsNotice] = useState<SectionNotice | null>(null);
  const effectiveRustfsDraft = rustfsDraft ?? rustfsConfigToDraft(rustfsConfig);

  useEffect(() => {
    async function loadRustfsConfig() {
      try {
        const config = await requestJson<RustfsStorageConfig>("/admin/storage/rustfs/config");
        setRustfsConfig(config);
        setRustfsDraft(rustfsConfigToDraft(config));
      } catch (error) {
        setRustfsLoadError(getErrorMessage(error));
      }
    }
    void loadRustfsConfig();
  }, []);

  async function saveRustfsConfig() {
    if (!effectiveRustfsDraft) return;
    setRustfsBusy(true);
    setRustfsNotice(null);
    try {
      const patch: RustfsStorageConfigPatch = {
        enabled: effectiveRustfsDraft.enabled,
        endpoint_url: effectiveRustfsDraft.endpointUrl,
        bucket: effectiveRustfsDraft.bucket,
        prefix: effectiveRustfsDraft.prefix,
        region: effectiveRustfsDraft.region,
        force_path_style: true,
        retention_days: effectiveRustfsDraft.retentionDays ?? 0
      };
      if (effectiveRustfsDraft.accessKey.trim()) {
        patch.access_key = effectiveRustfsDraft.accessKey.trim();
      }
      if (effectiveRustfsDraft.secretKey.trim()) {
        patch.secret_key = effectiveRustfsDraft.secretKey.trim();
      }
      const config = await patchJson<RustfsStorageConfig>("/admin/storage/rustfs/config", patch);
      setRustfsConfig(config);
      setRustfsDraft(rustfsConfigToDraft(config));
      toast.success("RustFS 설정을 저장했습니다.");
    } catch (error) {
      const message = getErrorMessage(error);
      setRustfsNotice({ tone: "error", text: message });
      toast.error("RustFS 설정 저장 실패", message);
    } finally {
      setRustfsBusy(false);
    }
  }

  async function checkRustfsConfig() {
    setRustfsBusy(true);
    setRustfsNotice(null);
    try {
      const result = await postJson<RustfsConnectionCheck>("/admin/storage/rustfs/check", {});
      setRustfsNotice({
        tone: result.ok ? "success" : "error",
        text: result.ok ? result.message ?? "연결되었습니다." : result.message ?? "연결 실패"
      });
    } catch (error) {
      setRustfsNotice({ tone: "error", text: getErrorMessage(error) });
    } finally {
      setRustfsBusy(false);
    }
  }

  return (
    <div className="grid two">
      <Panel title="VWorld 인증키">
        {loading ? (
          <div aria-busy="true" className="form-grid">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-44" />
          </div>
        ) : (
          <VWorldKeyForm
            apiKey={apiKey}
            resetApiKey={resetApiKey}
            saveApiKey={saveApiKey}
          />
        )}
      </Panel>
      <Panel title="현재 적용 상태">
        <div className="settings-status">
          <div>
            <span>적용 출처</span>
            <strong>{sourceLabels[source]}</strong>
          </div>
          <div>
            <span>.env 기본값</span>
            <strong>{envApiKey ? "설정됨" : "없음"}</strong>
          </div>
          <div>
            <span>지도 렌더링</span>
            <strong>{apiKey ? "VWorld WMTS 사용" : "좌표 프리뷰 fallback"}</strong>
          </div>
        </div>
        <div className="settings-icon">
          <KeyRound size={28} />
        </div>
      </Panel>
      <Panel
        badges={
          <HelpTip label="공개 API 키 도움말">
            DB에 활성 공개 API 키가 없으면 백엔드 환경변수 <code>KTG_VWORLD_API_KEY</code>가
            기본 key로 사용됩니다.
          </HelpTip>
        }
        title="공개 API 키"
      >
        <PublicApiKeysSection />
      </Panel>
      <Panel title="로그인 기록">
        <LoginHistorySection />
      </Panel>
      <Panel title="RustFS 저장소">
        {effectiveRustfsDraft ? (
          <RustfsConfigForm
            busy={rustfsBusy}
            config={rustfsConfig}
            draft={effectiveRustfsDraft}
            notice={rustfsNotice}
            onCheck={checkRustfsConfig}
            onDraftChange={setRustfsDraft}
            onSubmit={saveRustfsConfig}
          />
        ) : rustfsLoadError ? (
          <Alert role="alert" variant="destructive">
            <AlertDescription>{rustfsLoadError}</AlertDescription>
          </Alert>
        ) : (
          <div aria-busy="true" className="form-grid">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-44" />
          </div>
        )}
      </Panel>
    </div>
  );
}

type RustfsDraft = {
  enabled: boolean;
  endpointUrl: string;
  bucket: string;
  prefix: string;
  region: string;
  retentionDays: number | null;
  accessKey: string;
  secretKey: string;
};

type PublicApiKeysState = {
  busy: boolean;
  generatedKey: string | null;
  label: string;
  notice: SectionNotice | null;
  publicKeys: PublicApiKeySummary[] | null;
};

function PublicApiKeysSection() {
  const [state, setState] = useState<PublicApiKeysState>({
    busy: false,
    generatedKey: null,
    label: "",
    notice: null,
    publicKeys: null
  });

  const patchState = useCallback((patch: Partial<PublicApiKeysState>) => {
    setState((current) => ({ ...current, ...patch }));
  }, []);

  const loadPublicApiKeys = useCallback(async () => {
    patchState({ notice: null });
    try {
      patchState({ publicKeys: await requestJson<PublicApiKeySummary[]>("/admin/public-api-keys") });
    } catch (error) {
      patchState({ notice: { tone: "error", text: getErrorMessage(error) } });
    }
  }, [patchState]);

  useEffect(() => {
    void loadPublicApiKeys();
  }, [loadPublicApiKeys]);

  async function createPublicApiKey(event: FormEvent) {
    event.preventDefault();
    patchState({ busy: true, generatedKey: null, notice: null });
    try {
      const result = await postJson<PublicApiKeyCreateResponse>("/admin/public-api-keys", {
        label: state.label.trim() || null
      });
      savePublicApiKeyForRequests(result.key);
      setState((current) => ({
        ...current,
        generatedKey: result.key,
        label: "",
        notice: {
          tone: "success",
          text: "공개 API 키를 생성하고 이 브라우저의 API 요청 key로 적용했습니다."
        },
        publicKeys: [result.item, ...(current.publicKeys ?? [])]
      }));
    } catch (error) {
      patchState({ notice: { tone: "error", text: getErrorMessage(error) } });
    } finally {
      patchState({ busy: false });
    }
  }

  async function revokePublicApiKey(publicApiKeyId: string) {
    patchState({ busy: true, notice: null });
    try {
      const result = await deleteJson<PublicApiKeySummary>(
        `/admin/public-api-keys/${publicApiKeyId}`
      );
      clearPublicApiKeyForRequestsByHint(result.key_hint);
      setState((current) => ({
        ...current,
        notice: { tone: "success", text: "공개 API 키를 폐기했습니다." },
        publicKeys: (current.publicKeys ?? []).map((item) =>
          item.public_api_key_id === result.public_api_key_id ? result : item
        )
      }));
    } catch (error) {
      patchState({ notice: { tone: "error", text: getErrorMessage(error) } });
    } finally {
      patchState({ busy: false });
    }
  }

  return (
    <PublicApiKeyPanel
      busy={state.busy}
      generatedKey={state.generatedKey}
      label={state.label}
      notice={state.notice}
      publicKeys={state.publicKeys}
      onCopyGeneratedKey={async () => {
        if (!state.generatedKey) return;
        // navigator.clipboard is undefined in insecure contexts (plain-http LAN/IP origins),
        // which this internal console can be served over. Feature-detect and fall back to a
        // manual-copy hint (the generated-key input is readOnly + selects on focus) instead of
        // throwing an unhandled rejection that silently loses the once-shown key.
        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(state.generatedKey);
            patchState({ notice: { tone: "success", text: "생성된 키를 복사했습니다." } });
            return;
          }
        } catch {
          // fall through to the manual-copy hint
        }
        patchState({
          notice: {
            tone: "info",
            text: "이 브라우저에서 자동 복사를 쓸 수 없습니다. ‘생성된 키’ 입력란을 클릭해 전체 선택 후 Ctrl+C로 복사하세요."
          }
        });
      }}
      onCreate={createPublicApiKey}
      onClearGeneratedKey={() =>
        patchState({
          generatedKey: null,
          notice: { tone: "info", text: "생성된 키 표시를 지웠습니다." }
        })
      }
      onLabelChange={(label) => patchState({ label })}
      onRefresh={loadPublicApiKeys}
      onRevoke={revokePublicApiKey}
    />
  );
}

type LoginHistoryState = {
  error: string | null;
  events: AuditEvent[] | null;
};

function LoginHistorySection() {
  const [state, setState] = useState<LoginHistoryState>({ error: null, events: null });

  const loadLoginEvents = useCallback(async () => {
    setState((current) => ({ ...current, error: null }));
    try {
      const [logins, logouts] = await Promise.all([
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=50&action=admin_auth.login"),
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=50&action=admin_auth.logout")
      ]);
      setState({
        error: null,
        events: [...logins, ...logouts]
          .sort((left, right) => right.occurred_at.localeCompare(left.occurred_at))
          .slice(0, 50)
      });
    } catch (error) {
      setState((current) => ({ ...current, error: getErrorMessage(error) }));
    }
  }, []);

  useEffect(() => {
    void loadLoginEvents();
  }, [loadLoginEvents]);

  return (
    <LoginHistoryPanel
      error={state.error}
      events={state.events}
      onRefresh={loadLoginEvents}
    />
  );
}

function VWorldKeyForm({
  apiKey,
  resetApiKey,
  saveApiKey
}: {
  apiKey: string;
  resetApiKey: () => void;
  saveApiKey: (value: string) => void;
}) {
  const [draftValue, setDraftValue] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [saved, setSaved] = useState(false);
  const value = draftValue ?? apiKey;

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextValue = draftValue ?? apiKey;
    saveApiKey(nextValue);
    setDraftValue(null);
    setSaved(true);
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <Field>
        {/* HelpTip은 label 밖 형제 — label 내부 버튼은 RTL getByLabelText 다중 매치를 만든다. */}
        <span className="flex items-center gap-1">
          <FieldLabel htmlFor="vworld-api-key">VWorld 인증키</FieldLabel>
          <HelpTip label="VWorld 인증키 도움말">
            서버 환경변수 <code>KTG_VWORLD_API_KEY</code>(또는{" "}
            <code>NEXT_PUBLIC_VWORLD_API_KEY</code>) 값이 .env 기본값으로 쓰입니다. 여기서
            저장한 값은 이 브라우저에서만 우선 적용됩니다.
          </HelpTip>
        </span>
        <span className="flex items-center gap-2">
          <Input
            autoComplete="off"
            id="vworld-api-key"
            placeholder="VWorld WMTS 인증키"
            type={revealed ? "text" : "password"}
            value={value}
            onChange={(event) => {
              setSaved(false);
              setDraftValue(event.target.value);
            }}
          />
          <Button
            aria-label={revealed ? "키 숨기기" : "키 표시"}
            aria-pressed={revealed}
            size="icon-sm"
            type="button"
            variant="outline"
            onClick={() => setRevealed((current) => !current)}
          >
            {revealed ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
          </Button>
        </span>
      </Field>
      <div className="button-row">
        <Button type="submit">
          <Save aria-hidden="true" />
          저장
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            resetApiKey();
            setDraftValue(null);
            setSaved(true);
          }}
        >
          <RotateCcw aria-hidden="true" />
          기본값
        </Button>
      </div>
      {saved ? (
        <Alert role="status" variant="success">
          <AlertDescription>지도 설정을 저장했습니다.</AlertDescription>
        </Alert>
      ) : null}
    </form>
  );
}

function LoginHistoryPanel({
  error,
  events,
  onRefresh
}: {
  error: string | null;
  events: AuditEvent[] | null;
  onRefresh: () => Promise<void>;
}) {
  return (
    <div className="form-grid">
      <div className="button-row">
        <RefreshButton onClick={() => void onRefresh()} />
      </div>
      {error ? (
        <Alert role="alert" variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="public-key-list">
        {events === null ? (
          error ? null : (
            <>
              <Skeleton className="h-[54px] w-full" />
              <Skeleton className="h-[54px] w-full" />
              <Skeleton className="h-[54px] w-full" />
            </>
          )
        ) : events.length === 0 ? (
          <EmptyState>저장된 로그인 기록이 없습니다.</EmptyState>
        ) : (
          events.map((event) => (
            <div className="public-key-item" key={event.audit_event_id}>
              <div>
                <strong>{loginEventTitle(event)}</strong>
                <span>{loginEventDetail(event)}</span>
              </div>
              <div className="public-key-actions">
                <Badge
                  data-state={event.outcome === "succeeded" ? "active" : "revoked"}
                  tone={event.outcome === "succeeded" ? "ok" : "error"}
                >
                  {loginOutcomeLabel(event.outcome)}
                </Badge>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function loginEventTitle(event: AuditEvent): string {
  const payload = event.payload_redacted ?? {};
  const username =
    typeof payload.attempted_username === "string" ? payload.attempted_username : "unknown";
  const type = event.action === "admin_auth.logout" ? "로그아웃" : "로그인";
  return `${type} · ${username} · ${event.occurred_at}`;
}

function loginEventDetail(event: AuditEvent): string {
  const payload = event.payload_redacted ?? {};
  const reason = typeof payload.reason === "string" ? payload.reason : "-";
  const ip = event.client_ip_hash ? `ip:${event.client_ip_hash.slice(0, 10)}` : "ip:-";
  const ua = event.user_agent_hash ? `ua:${event.user_agent_hash.slice(0, 10)}` : "ua:-";
  return `${reason} · ${ip} · ${ua}`;
}

function loginOutcomeLabel(outcome: AuditEvent["outcome"]): string {
  if (outcome === "succeeded") return "성공";
  if (outcome === "denied") return "거부";
  if (outcome === "failed") return "실패";
  return outcome;
}

function PublicApiKeyPanel({
  busy,
  generatedKey,
  label,
  notice,
  publicKeys,
  onCopyGeneratedKey,
  onCreate,
  onClearGeneratedKey,
  onLabelChange,
  onRefresh,
  onRevoke
}: {
  busy: boolean;
  generatedKey: string | null;
  label: string;
  notice: SectionNotice | null;
  publicKeys: PublicApiKeySummary[] | null;
  onCopyGeneratedKey: () => Promise<void>;
  onCreate: (event: FormEvent) => Promise<void>;
  onClearGeneratedKey: () => void;
  onLabelChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onRevoke: (publicApiKeyId: string) => Promise<void>;
}) {
  return (
    <div className="form-grid">
      <form className="form-grid" onSubmit={onCreate}>
        <Field>
          <FieldLabel htmlFor="public-api-key-label">키 이름</FieldLabel>
          <Input
            id="public-api-key-label"
            maxLength={80}
            placeholder="운영 콘솔, 테스트 클라이언트"
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
          />
        </Field>
        <div className="button-row">
          <Button disabled={busy} type="submit">
            <KeyRound aria-hidden="true" />
            랜덤 키 생성
          </Button>
          <RefreshButton busy={busy} onClick={() => void onRefresh()} />
        </div>
      </form>
      {generatedKey ? (
        <div className="generated-key-box">
          <Field>
            <FieldLabel htmlFor="generated-public-api-key">생성된 키</FieldLabel>
            <Input
              id="generated-public-api-key"
              readOnly
              value={generatedKey}
              onFocus={(event) => event.currentTarget.select()}
            />
          </Field>
          <div className="button-row">
            <Button type="button" variant="outline" onClick={() => void onCopyGeneratedKey()}>
              <Copy aria-hidden="true" />
              복사
            </Button>
            <Button type="button" variant="outline" onClick={onClearGeneratedKey}>
              <EyeOff aria-hidden="true" />
              지우기
            </Button>
          </div>
          <p className="form-note">이 키는 지금 한 번만 표시됩니다.</p>
        </div>
      ) : null}
      <div className="public-key-list">
        {publicKeys === null ? (
          notice?.tone === "error" ? null : (
            <>
              <Skeleton className="h-[54px] w-full" />
              <Skeleton className="h-[54px] w-full" />
            </>
          )
        ) : publicKeys.length === 0 ? (
          <EmptyState>등록된 공개 API 키가 없습니다.</EmptyState>
        ) : (
          publicKeys.map((item) => (
            <div className="public-key-item" key={item.public_api_key_id}>
              <div>
                <strong>{item.label ?? "이름 없음"}</strong>
                <span>····{item.key_hint}</span>
              </div>
              <div className="public-key-actions">
                <Badge
                  data-state={item.state}
                  tone={item.state === "active" ? "ok" : "neutral"}
                >
                  {item.state === "active" ? "활성" : "폐기됨"}
                </Badge>
                {item.state === "active" ? (
                  <ConfirmActionDialog
                    confirmLabel="폐기"
                    description={
                      <>
                        ‘{item.label ?? `····${item.key_hint}`}’ 키를 폐기합니다. 폐기한 키는
                        즉시 무효화되며 되돌릴 수 없습니다.
                      </>
                    }
                    roles={["source_file_manager"]}
                    title="공개 API 키 폐기"
                    trigger={
                      <Button
                        aria-label={`${item.label ?? item.key_hint} 키 폐기`}
                        disabled={busy}
                        size="icon-sm"
                        type="button"
                        variant="outline"
                      >
                        <Trash2 aria-hidden="true" />
                      </Button>
                    }
                    onConfirm={() => void onRevoke(item.public_api_key_id)}
                  />
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>
      {notice ? <NoticeAlert notice={notice} /> : null}
    </div>
  );
}

type RustfsDraftErrors = Partial<Record<"endpointUrl" | "bucket", string>>;

function validateRustfsDraft(draft: RustfsDraft): RustfsDraftErrors {
  if (!draft.enabled) return {};
  const errors: RustfsDraftErrors = {};
  const endpointResult = httpUrlSchema.safeParse(draft.endpointUrl);
  if (!endpointResult.success) {
    errors.endpointUrl = endpointResult.error.issues[0]?.message;
  }
  const bucketResult = s3BucketSchema.safeParse(draft.bucket);
  if (!bucketResult.success) {
    errors.bucket = bucketResult.error.issues[0]?.message;
  }
  return errors;
}

function RustfsConfigForm({
  busy,
  config,
  draft,
  notice,
  onCheck,
  onDraftChange,
  onSubmit
}: {
  busy: boolean;
  config: RustfsStorageConfig | null;
  draft: RustfsDraft;
  notice: SectionNotice | null;
  onCheck: () => Promise<void>;
  onDraftChange: (draft: RustfsDraft) => void;
  onSubmit: () => Promise<void>;
}) {
  const [showErrors, setShowErrors] = useState(false);
  const errors = validateRustfsDraft(draft);
  const visibleErrors: RustfsDraftErrors = showErrors ? errors : {};
  const fieldsDisabled = !draft.enabled;

  function patch(patchValue: Partial<RustfsDraft>) {
    onDraftChange({ ...draft, ...patchValue });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (Object.keys(errors).length > 0) {
      setShowErrors(true);
      return;
    }
    setShowErrors(false);
    void onSubmit();
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <Field orientation="horizontal">
        <Checkbox
          checked={draft.enabled}
          id="rustfs-enabled"
          onCheckedChange={(checked) => patch({ enabled: checked === true })}
        />
        <FieldLabel htmlFor="rustfs-enabled">RustFS 업로드 저장소 사용</FieldLabel>
      </Field>
      <div className="form-field-grid two">
        <Field data-invalid={visibleErrors.endpointUrl ? true : undefined}>
          <FieldLabel htmlFor="rustfs-endpoint">Endpoint URL</FieldLabel>
          <Input
            aria-invalid={visibleErrors.endpointUrl ? true : undefined}
            disabled={fieldsDisabled}
            id="rustfs-endpoint"
            placeholder="http://127.0.0.1:12101"
            value={draft.endpointUrl}
            onChange={(event) => patch({ endpointUrl: event.target.value })}
          />
          {visibleErrors.endpointUrl ? <FieldError>{visibleErrors.endpointUrl}</FieldError> : null}
        </Field>
        <Field data-invalid={visibleErrors.bucket ? true : undefined}>
          <FieldLabel htmlFor="rustfs-bucket">Bucket</FieldLabel>
          <Input
            aria-invalid={visibleErrors.bucket ? true : undefined}
            disabled={fieldsDisabled}
            id="rustfs-bucket"
            value={draft.bucket}
            onChange={(event) => patch({ bucket: event.target.value })}
          />
          {visibleErrors.bucket ? <FieldError>{visibleErrors.bucket}</FieldError> : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="rustfs-prefix">Prefix</FieldLabel>
          <Input
            disabled={fieldsDisabled}
            id="rustfs-prefix"
            placeholder="예: uploads/"
            value={draft.prefix}
            onChange={(event) => patch({ prefix: event.target.value })}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="rustfs-region">Region</FieldLabel>
          <Input
            disabled={fieldsDisabled}
            id="rustfs-region"
            placeholder="기본값: us-east-1"
            value={draft.region}
            onChange={(event) => patch({ region: event.target.value })}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="rustfs-access-key">Access key</FieldLabel>
          <Input
            autoComplete="off"
            disabled={fieldsDisabled}
            id="rustfs-access-key"
            placeholder={config?.access_key.configured ? `설정됨 ····${config.access_key.hint ?? ""}` : "미설정"}
            type="password"
            value={draft.accessKey}
            onChange={(event) => patch({ accessKey: event.target.value })}
          />
          <FieldDescription>비워 두면 기존 값을 유지합니다.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="rustfs-secret-key">Secret key</FieldLabel>
          <Input
            autoComplete="off"
            disabled={fieldsDisabled}
            id="rustfs-secret-key"
            placeholder={config?.secret_key.configured ? `설정됨 ····${config.secret_key.hint ?? ""}` : "미설정"}
            type="password"
            value={draft.secretKey}
            onChange={(event) => patch({ secretKey: event.target.value })}
          />
          <FieldDescription>비워 두면 기존 값을 유지합니다.</FieldDescription>
        </Field>
        <NumberField
          description="0 = 무기한 보존"
          disabled={fieldsDisabled}
          id="rustfs-retention-days"
          label="보존 기간"
          max={36500}
          min={0}
          suffix="일"
          value={draft.retentionDays}
          onChange={(retentionDays) => patch({ retentionDays })}
        />
      </div>
      <div className="button-row">
        <Button disabled={busy} type="submit">
          <Save aria-hidden="true" />
          저장
        </Button>
        <Button
          disabled={busy || !draft.enabled}
          type="button"
          variant="outline"
          onClick={() => void onCheck()}
        >
          연결 테스트
        </Button>
        <HelpTip label="연결 테스트 도움말">
          연결 테스트는 서버에 저장된 설정 기준으로 실행됩니다. 값을 바꿨다면 먼저 저장하세요.
        </HelpTip>
      </div>
      {notice ? <NoticeAlert notice={notice} /> : null}
    </form>
  );
}

function rustfsConfigToDraft(config: RustfsStorageConfig | null): RustfsDraft | null {
  if (!config) return null;
  return {
    enabled: config.enabled,
    endpointUrl: config.endpoint_url,
    bucket: config.bucket,
    prefix: config.prefix,
    region: config.region,
    retentionDays: config.retention_days,
    accessKey: "",
    secretKey: ""
  };
}
