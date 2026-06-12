"use client";

import { KeyRound, RefreshCw, RotateCcw, Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import {
  RustfsConnectionCheck,
  RustfsStorageConfig,
  RustfsStorageConfigPatch,
  patchJson,
  postJson,
  requestJson
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
