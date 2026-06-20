"use client";

import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";
import {
  errorRecoveryMessage,
  errorReloadStorageKey,
  isLikelyRecoverableNextRuntimeError
} from "@/lib/error-recovery";

type AppErrorPanelProps = {
  error: Error & { digest?: string };
  reset?: () => void;
  standalone?: boolean;
};

// Suppress an auto-reload only if the previous one was this recent (i.e. an
// immediate reload→re-error loop). Older than this and a fresh transient error
// is allowed to self-heal again, so the guard never permanently disables itself.
const RELOAD_GUARD_WINDOW_MS = 10_000;

function goBack() {
  if (window.history.length > 1) {
    window.history.back();
    return;
  }
  window.location.assign("/debug/geocode");
}

export function AppErrorPanel({ error, reset, standalone = false }: AppErrorPanelProps) {
  const recoverable = useMemo(() => isLikelyRecoverableNextRuntimeError(error), [error]);
  const details = useMemo(() => errorRecoveryMessage(error), [error]);

  useEffect(() => {
    if (!recoverable || typeof window === "undefined") {
      return;
    }

    const key = errorReloadStorageKey(window.location.pathname);
    const lastReloadAt = Number(window.sessionStorage.getItem(key));
    if (Number.isFinite(lastReloadAt) && Date.now() - lastReloadAt < RELOAD_GUARD_WINDOW_MS) {
      return;
    }

    window.sessionStorage.setItem(key, String(Date.now()));
    window.location.reload();
  }, [recoverable]);

  const retry = () => {
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(errorReloadStorageKey(window.location.pathname));
    }
    if (reset) {
      reset();
      return;
    }
    window.location.reload();
  };

  return (
    <section className={standalone ? "app-error-shell standalone" : "app-error-shell"} role="alert">
      <div className="app-error-panel">
        <p className="eyebrow">UI runtime error</p>
        <h1>페이지를 다시 불러오지 못했습니다</h1>
        <p className="app-error-copy">
          {recoverable
            ? "현재 탭의 화면 런타임 상태가 서버와 맞지 않아 새로고침이 필요합니다."
            : "현재 탭의 UI 상태가 서버와 맞지 않거나, 화면 렌더링 중 오류가 발생했습니다."}
        </p>
        <div className="button-row">
          <button className="button" onClick={retry} type="button">
            <RefreshCw size={16} />
            다시 시도
          </button>
          <button className="button secondary" onClick={goBack} type="button">
            <ArrowLeft size={16} />
            이전 화면
          </button>
        </div>
        <details className="app-error-details">
          <summary>오류 정보</summary>
          <pre>{details || "no details"}</pre>
        </details>
      </div>
    </section>
  );
}
