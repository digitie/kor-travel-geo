"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, backendPath, type LoadJobStatus } from "@/lib/api";
import { terminalJobState } from "@/lib/backup-workflow";

export type EventSourceFactory = (url: string) => EventSource;

/**
 * Subscribe to the live ``status`` SSE stream for a backup/restore job (T-251, reusing the
 * T-203 upload-session SSE pattern). The same-origin proxy streams the admin
 * ``GET /v1/admin/jobs/{job_id}/events`` ``text/event-stream`` through with admin auth.
 *
 * Returns the latest ``LoadJobStatus`` frame, or null until the first frame. Closes on a
 * terminal state (and calls ``onTerminal``) so the browser does not auto-reconnect a finished
 * stream. Returns null (callers keep their react-query/interval polling fallback) when:
 *  - ``jobId`` is null or ``enabled`` is false,
 *  - ``EventSource`` is unavailable (SSR / jsdom unit tests with no injected factory).
 */
export function useJobEvents(
  jobId: string | null,
  options: {
    enabled?: boolean;
    onTerminal?: () => void;
    eventSourceFactory?: EventSourceFactory;
  } = {}
): LoadJobStatus | null {
  const { enabled = true, onTerminal, eventSourceFactory } = options;
  const [eventState, setEventState] = useState<{
    enabled: boolean;
    event: LoadJobStatus | null;
    jobId: string | null;
  }>({ enabled, event: null, jobId });
  const onTerminalRef = useRef(onTerminal);
  const stateIsStale = eventState.jobId !== jobId || eventState.enabled !== enabled;

  if (stateIsStale) {
    setEventState({ enabled, event: null, jobId });
  }

  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  useEffect(() => {
    if (!jobId || !enabled) {
      return;
    }
    const factory =
      eventSourceFactory ??
      (typeof EventSource !== "undefined" ? (url: string) => new EventSource(url) : null);
    if (!factory) {
      return;
    }

    const url = `${API_BASE}${backendPath(`/admin/jobs/${jobId}/events`)}`;
    const source = factory(url);

    const handle = (message: MessageEvent) => {
      let parsed: LoadJobStatus;
      try {
        parsed = JSON.parse(message.data) as LoadJobStatus;
      } catch {
        return; // ignore malformed frames
      }
      setEventState({ enabled, event: parsed, jobId });
      if (terminalJobState(parsed.state)) {
        source.close();
        onTerminalRef.current?.();
      }
    };

    source.addEventListener("status", handle as EventListener);
    source.onerror = () => {
      // Stream dropped/ended; close and let the caller's polling take over.
      source.close();
    };

    return () => {
      source.removeEventListener("status", handle as EventListener);
      source.close();
    };
  }, [jobId, enabled, eventSourceFactory]);

  return stateIsStale || !enabled ? null : eventState.event;
}
