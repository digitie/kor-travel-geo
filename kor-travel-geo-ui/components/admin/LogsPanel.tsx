"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage, requestJson } from "@/lib/api";

const LIMIT_OPTIONS = [50, 200, 500] as const;

export function LogsPanel() {
  const [lines, setLines] = useState<string[] | null>(null);
  const [limit, setLimit] = useState<number>(200);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextLimit: number) => {
    setBusy(true);
    try {
      setLines(await requestJson<string[]>(`/admin/logs?limit=${nextLimit}`));
      setError(null);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(limit);
  }, [limit, load]);

  return (
    <Panel
      title="최근 로그"
      actions={
        <>
          <span className="w-24 shrink-0">
            <NativeSelect
              aria-label="표시 줄 수"
              value={String(limit)}
              onChange={(event) => setLimit(Number(event.target.value))}
            >
              {LIMIT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}줄
                </option>
              ))}
            </NativeSelect>
          </span>
          <RefreshButton busy={busy} onClick={() => void load(limit)} />
        </>
      }
    >
      {error ? (
        <Alert role="alert" variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {lines === null ? (
        error ? null : <Skeleton className="h-48 w-full" />
      ) : (
        <pre className="json-box">
          {lines.length === 0
            ? "NO LOGS"
            : lines.map((line, index) => (
                // 로그 tail은 append-only 스냅샷이라 위치가 곧 identity다 — 내용 접두를
                // 섞어 재조회 시 안정적인 key를 만든다.
                <span className={logLineClass(line)} key={`${index}:${line.slice(0, 40)}`}>
                  {line}
                  {"\n"}
                </span>
              ))}
        </pre>
      )}
    </Panel>
  );
}

/** 로그 레벨별 강조 — ERROR 계열은 붉게, WARN 계열은 노랗게 (어두운 json-box 배경 기준). */
function logLineClass(line: string): string | undefined {
  if (/\b(ERROR|CRITICAL|FATAL)\b/.test(line)) return "font-semibold text-red-300";
  if (/\bWARN(ING)?\b/.test(line)) return "text-amber-300";
  return undefined;
}
