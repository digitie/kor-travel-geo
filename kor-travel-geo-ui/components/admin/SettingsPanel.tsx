"use client";

import { Copy, EyeOff, KeyRound, RefreshCw, RotateCcw, Save, Trash2 } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import {
  AuditEvent,
  RustfsConnectionCheck,
  RustfsStorageConfig,
  RustfsStorageConfigPatch,
  PublicApiKeyCreateResponse,
  PublicApiKeySummary,
  clearPublicApiKeyForRequestsByHint,
  deleteJson,
  patchJson,
  postJson,
  requestJson,
  savePublicApiKeyForRequests
} from "@/lib/api";
import { useVWorldApiKey } from "@/lib/vworld-key";

const sourceLabels = {
  browser: "브라우저 저장값",
  empty: "미설정",
  env: ".env 기본값",
  loading: "확인 중"
};

export function SettingsPanel() {
  const { apiKey, envApiKey, loading, resetApiKey, saveApiKey, source } = useVWorldApiKey();
  const [rustfsConfig, setRustfsConfig] = useState<RustfsStorageConfig | null>(null);
  const [rustfsDraft, setRustfsDraft] = useState<RustfsDraft | null>(null);
  const [rustfsBusy, setRustfsBusy] = useState(false);
  const [rustfsMessage, setRustfsMessage] = useState<string | null>(null);
  const effectiveRustfsDraft = rustfsDraft ?? rustfsConfigToDraft(rustfsConfig);

  useEffect(() => {
    async function loadRustfsConfig() {
      try {
        const config = await requestJson<RustfsStorageConfig>("/admin/storage/rustfs/config");
        setRustfsConfig(config);
        setRustfsDraft(rustfsConfigToDraft(config));
      } catch (error) {
        setRustfsMessage(error instanceof Error ? error.message : String(error));
      }
    }
    void loadRustfsConfig();
  }, []);

  async function saveRustfsConfig(event: FormEvent) {
    event.preventDefault();
    if (!effectiveRustfsDraft) return;
    setRustfsBusy(true);
    setRustfsMessage(null);
    try {
      const patch: RustfsStorageConfigPatch = {
        enabled: effectiveRustfsDraft.enabled,
        endpoint_url: effectiveRustfsDraft.endpointUrl,
        bucket: effectiveRustfsDraft.bucket,
        prefix: effectiveRustfsDraft.prefix,
        region: effectiveRustfsDraft.region,
        force_path_style: true,
        retention_days: Number(effectiveRustfsDraft.retentionDays || 0)
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
      setRustfsMessage("RustFS 설정을 저장했습니다.");
    } catch (error) {
      setRustfsMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRustfsBusy(false);
    }
  }

  async function checkRustfsConfig() {
    setRustfsBusy(true);
    setRustfsMessage(null);
    try {
      const result = await postJson<RustfsConnectionCheck>("/admin/storage/rustfs/check", {});
      setRustfsMessage(result.ok ? result.message ?? "연결되었습니다." : result.message ?? "연결 실패");
    } catch (error) {
      setRustfsMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRustfsBusy(false);
    }
  }

  return (
    <div className="grid two">
      <Panel title="VWorld 인증키">
        {loading ? (
          <div className="form-grid">
            <p className="form-note">설정을 불러오는 중입니다.</p>
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
      <Panel title="공개 API 키">
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
            message={rustfsMessage}
            onCheck={checkRustfsConfig}
            onDraftChange={setRustfsDraft}
            onSubmit={saveRustfsConfig}
          />
        ) : (
          <div className="form-grid">
            <p className="form-note">RustFS 설정을 불러오는 중입니다.</p>
            {rustfsMessage ? <p className="form-note">{rustfsMessage}</p> : null}
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
  retentionDays: string;
  accessKey: string;
  secretKey: string;
};

type PublicApiKeysState = {
  busy: boolean;
  generatedKey: string | null;
  label: string;
  message: string | null;
  publicKeys: PublicApiKeySummary[] | null;
};

function PublicApiKeysSection() {
  const [state, setState] = useState<PublicApiKeysState>({
    busy: false,
    generatedKey: null,
    label: "",
    message: null,
    publicKeys: null
  });

  const patchState = useCallback((patch: Partial<PublicApiKeysState>) => {
    setState((current) => ({ ...current, ...patch }));
  }, []);

  const loadPublicApiKeys = useCallback(async () => {
    patchState({ message: null });
    try {
      patchState({ publicKeys: await requestJson<PublicApiKeySummary[]>("/admin/public-api-keys") });
    } catch (error) {
      patchState({ message: error instanceof Error ? error.message : String(error) });
    }
  }, [patchState]);

  useEffect(() => {
    void loadPublicApiKeys();
  }, [loadPublicApiKeys]);

  async function createPublicApiKey(event: FormEvent) {
    event.preventDefault();
    patchState({ busy: true, generatedKey: null, message: null });
    try {
      const result = await postJson<PublicApiKeyCreateResponse>("/admin/public-api-keys", {
        label: state.label.trim() || null
      });
      savePublicApiKeyForRequests(result.key);
      setState((current) => ({
        ...current,
        generatedKey: result.key,
        label: "",
        message: "공개 API 키를 생성하고 이 브라우저의 API 요청 key로 적용했습니다.",
        publicKeys: [result.item, ...(current.publicKeys ?? [])]
      }));
    } catch (error) {
      patchState({ message: error instanceof Error ? error.message : String(error) });
    } finally {
      patchState({ busy: false });
    }
  }

  async function revokePublicApiKey(publicApiKeyId: string) {
    patchState({ busy: true, message: null });
    try {
      const result = await deleteJson<PublicApiKeySummary>(
        `/admin/public-api-keys/${publicApiKeyId}`
      );
      clearPublicApiKeyForRequestsByHint(result.key_hint);
      setState((current) => ({
        ...current,
        message: "공개 API 키를 폐기했습니다.",
        publicKeys: (current.publicKeys ?? []).map((item) =>
          item.public_api_key_id === result.public_api_key_id ? result : item
        )
      }));
    } catch (error) {
      patchState({ message: error instanceof Error ? error.message : String(error) });
    } finally {
      patchState({ busy: false });
    }
  }

  return (
    <PublicApiKeyPanel
      busy={state.busy}
      generatedKey={state.generatedKey}
      label={state.label}
      message={state.message}
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
            patchState({ message: "생성된 키를 복사했습니다." });
            return;
          }
        } catch {
          // fall through to the manual-copy hint
        }
        patchState({
          message: "이 브라우저에서 자동 복사를 쓸 수 없습니다. ‘생성된 키’ 입력란을 클릭해 전체 선택 후 Ctrl+C로 복사하세요."
        });
      }}
      onCreate={createPublicApiKey}
      onClearGeneratedKey={() =>
        patchState({ generatedKey: null, message: "생성된 키 표시를 지웠습니다." })
      }
      onLabelChange={(label) => patchState({ label })}
      onRefresh={loadPublicApiKeys}
      onRevoke={revokePublicApiKey}
    />
  );
}

type LoginHistoryState = {
  events: AuditEvent[] | null;
  message: string | null;
};

function LoginHistorySection() {
  const [state, setState] = useState<LoginHistoryState>({ events: null, message: null });

  const loadLoginEvents = useCallback(async () => {
    setState((current) => ({ ...current, message: null }));
    try {
      const [logins, logouts] = await Promise.all([
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=50&action=admin_auth.login"),
        requestJson<AuditEvent[]>("/admin/ops/audit-events?limit=50&action=admin_auth.logout")
      ]);
      setState({
        events: [...logins, ...logouts]
          .sort((left, right) => right.occurred_at.localeCompare(left.occurred_at))
          .slice(0, 50),
        message: null
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        message: error instanceof Error ? error.message : String(error)
      }));
    }
  }, []);

  useEffect(() => {
    void loadLoginEvents();
  }, [loadLoginEvents]);

  return (
    <LoginHistoryPanel
      events={state.events}
      message={state.message}
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
      <div className="field">
        <label htmlFor="vworld-api-key">NEXT_PUBLIC_VWORLD_API_KEY</label>
        <input
          autoComplete="off"
          id="vworld-api-key"
          placeholder="VWorld WMTS 인증키"
          value={value}
          onChange={(event) => {
            setSaved(false);
            setDraftValue(event.target.value);
          }}
        />
      </div>
      <div className="button-row">
        <button className="button" type="submit">
          <Save size={16} />
          저장
        </button>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => {
            resetApiKey();
            setDraftValue(null);
            setSaved(true);
          }}
        >
          <RotateCcw size={16} />
          기본값
        </button>
      </div>
      {saved ? <p className="form-note">지도 설정을 저장했습니다.</p> : null}
    </form>
  );
}

function LoginHistoryPanel({
  events,
  message,
  onRefresh
}: {
  events: AuditEvent[] | null;
  message: string | null;
  onRefresh: () => Promise<void>;
}) {
  return (
    <div className="form-grid">
      <div className="button-row">
        <button
          className="button button-secondary"
          onClick={() => void onRefresh()}
          type="button"
        >
          <RefreshCw size={16} />
          새로고침
        </button>
      </div>
      <div className="public-key-list">
        {events === null ? (
          <p className="form-note">로그인 기록을 불러오는 중입니다.</p>
        ) : events.length === 0 ? (
          <p className="form-note">저장된 로그인 기록이 없습니다.</p>
        ) : (
          events.map((event) => (
            <div className="public-key-item" key={event.audit_event_id}>
              <div>
                <strong>{loginEventTitle(event)}</strong>
                <span>{loginEventDetail(event)}</span>
              </div>
              <div className="public-key-actions">
                <span data-state={event.outcome === "succeeded" ? "active" : "revoked"}>
                  {loginOutcomeLabel(event.outcome)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
      {message ? <p className="form-note">{message}</p> : null}
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
  message,
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
  message: string | null;
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
        <div className="field">
          <label htmlFor="public-api-key-label">키 이름</label>
          <input
            id="public-api-key-label"
            maxLength={80}
            placeholder="운영 콘솔, 테스트 클라이언트"
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
          />
        </div>
        <div className="button-row">
          <button className="button" disabled={busy} type="submit">
            <KeyRound size={16} />
            랜덤 키 생성
          </button>
          <button
            className="button button-secondary"
            disabled={busy}
            onClick={() => void onRefresh()}
            type="button"
          >
            <RefreshCw size={16} />
            새로고침
          </button>
        </div>
        <p className="form-note">
          DB에 활성 공개 API 키가 없으면 백엔드의 KTG_VWORLD_API_KEY가 기본 key로
          사용됩니다. 생성된 키는 이 브라우저의 API 요청 key로 적용됩니다.
        </p>
      </form>
      {generatedKey ? (
        <div className="generated-key-box">
          <div className="field">
            <label htmlFor="generated-public-api-key">생성된 키</label>
            <input
              id="generated-public-api-key"
              readOnly
              value={generatedKey}
              onFocus={(event) => event.currentTarget.select()}
            />
          </div>
          <button
            className="button button-secondary"
            onClick={() => void onCopyGeneratedKey()}
            type="button"
          >
            <Copy size={16} />
            복사
          </button>
          <button
            className="button button-secondary"
            onClick={onClearGeneratedKey}
            type="button"
          >
            <EyeOff size={16} />
            지우기
          </button>
          <p className="form-note">이 키는 지금 한 번만 표시됩니다.</p>
        </div>
      ) : null}
      <div className="public-key-list">
        {publicKeys === null ? (
          <p className="form-note">공개 API 키 목록을 불러오는 중입니다.</p>
        ) : publicKeys.length === 0 ? (
          <p className="form-note">등록된 공개 API 키가 없습니다.</p>
        ) : (
          publicKeys.map((item) => (
            <div className="public-key-item" key={item.public_api_key_id}>
              <div>
                <strong>{item.label ?? "이름 없음"}</strong>
                <span>····{item.key_hint}</span>
              </div>
              <div className="public-key-actions">
                <span data-state={item.state}>{item.state === "active" ? "활성" : "폐기됨"}</span>
                {item.state === "active" ? (
                  <button
                    aria-label={`${item.label ?? item.key_hint} 키 폐기`}
                    className="icon-button"
                    disabled={busy}
                    onClick={() => void onRevoke(item.public_api_key_id)}
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>
      {message ? <p className="form-note">{message}</p> : null}
    </div>
  );
}

function RustfsConfigForm({
  busy,
  config,
  draft,
  message,
  onCheck,
  onDraftChange,
  onSubmit
}: {
  busy: boolean;
  config: RustfsStorageConfig | null;
  draft: RustfsDraft;
  message: string | null;
  onCheck: () => Promise<void>;
  onDraftChange: (draft: RustfsDraft) => void;
  onSubmit: (event: FormEvent) => Promise<void>;
}) {
  function patch(patchValue: Partial<RustfsDraft>) {
    onDraftChange({ ...draft, ...patchValue });
  }

  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label className="checkbox-row">
        <input
          checked={draft.enabled}
          onChange={(event) => patch({ enabled: event.target.checked })}
          type="checkbox"
        />
        RustFS 업로드 저장소 사용
      </label>
      <div className="form-field-grid two">
        <div className="field">
          <label htmlFor="rustfs-endpoint">Endpoint URL</label>
          <input
            id="rustfs-endpoint"
            onChange={(event) => patch({ endpointUrl: event.target.value })}
            placeholder="http://127.0.0.1:12101"
            value={draft.endpointUrl}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-bucket">Bucket</label>
          <input
            id="rustfs-bucket"
            onChange={(event) => patch({ bucket: event.target.value })}
            value={draft.bucket}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-prefix">Prefix</label>
          <input
            id="rustfs-prefix"
            onChange={(event) => patch({ prefix: event.target.value })}
            value={draft.prefix}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-region">Region</label>
          <input
            id="rustfs-region"
            onChange={(event) => patch({ region: event.target.value })}
            value={draft.region}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-access-key">Access key</label>
          <input
            autoComplete="off"
            id="rustfs-access-key"
            onChange={(event) => patch({ accessKey: event.target.value })}
            placeholder={config?.access_key.configured ? `설정됨 ····${config.access_key.hint ?? ""}` : "미설정"}
            value={draft.accessKey}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-secret-key">Secret key</label>
          <input
            autoComplete="off"
            id="rustfs-secret-key"
            onChange={(event) => patch({ secretKey: event.target.value })}
            placeholder={config?.secret_key.configured ? `설정됨 ····${config.secret_key.hint ?? ""}` : "미설정"}
            type="password"
            value={draft.secretKey}
          />
        </div>
        <div className="field">
          <label htmlFor="rustfs-retention-days">보존 기간</label>
          <input
            id="rustfs-retention-days"
            min={0}
            onChange={(event) => patch({ retentionDays: event.target.value })}
            type="number"
            value={draft.retentionDays}
          />
        </div>
      </div>
      <div className="button-row">
        <button className="button" disabled={busy} type="submit">
          <Save size={16} />
          저장
        </button>
        <button
          className="button secondary"
          disabled={busy || !draft.enabled}
          onClick={() => void onCheck()}
          type="button"
        >
          <RefreshCw size={16} />
          연결 테스트
        </button>
      </div>
      <p className="form-note">보존 기간 `0`은 무기한 보존입니다. Secret 입력칸은 비워 두면 기존 값을 유지합니다.</p>
      {message ? <p className="form-note">{message}</p> : null}
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
    retentionDays: String(config.retention_days),
    accessKey: "",
    secretKey: ""
  };
}
