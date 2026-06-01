"use client";

import { KeyRound, RotateCcw, Save } from "lucide-react";
import { FormEvent, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { useVWorldApiKey } from "@/lib/vworld-key";

const sourceLabels = {
  browser: "브라우저 저장값",
  empty: "미설정",
  env: ".env 기본값",
  loading: "확인 중"
};

export function SettingsPanel() {
  const { apiKey, envApiKey, loading, resetApiKey, saveApiKey, source } = useVWorldApiKey();

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
    </div>
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
