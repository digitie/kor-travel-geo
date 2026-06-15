"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, backendPath } from "@/lib/api";
import {
  isTerminalUploadState,
  sourceFilesPaths,
  type SourceUploadProgressEvent
} from "@/lib/source-files";

export type EventSourceFactory = (url: string) => EventSource;

/**
 * Subscribe to the live ``source_upload.progress`` SSE stream for an in-flight
 * upload session (T-209). The same-origin proxy streams ``text/event-stream``
 * through with the admin auth it injects for every other admin call.
 *
 * Falls back to nothing (callers keep their react-query polling) when:
 *  - ``sessionId`` is null or ``enabled`` is false,
 *  - ``EventSource`` is unavailable (SSR / jsdom unit tests with no factory).
 *
 * Closes the stream on a terminal-state event (and calls ``onTerminal``) so the
 * browser's auto-reconnect does not re-open a finished stream.
 */
export function useUploadSessionEvents(
  sessionId: string | null,
  options: {
    enabled?: boolean;
    onTerminal?: () => void;
    eventSourceFactory?: EventSourceFactory;
  } = {}
): SourceUploadProgressEvent | null {
  const { enabled = true, onTerminal, eventSourceFactory } = options;
  const [eventState, setEventState] = useState<{
    enabled: boolean;
    event: SourceUploadProgressEvent | null;
    sessionId: string | null;
  }>({ enabled, event: null, sessionId });
  const onTerminalRef = useRef(onTerminal);
  const stateIsStale = eventState.sessionId !== sessionId || eventState.enabled !== enabled;

  if (stateIsStale) {
    setEventState({ enabled, event: null, sessionId });
  }

  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  useEffect(() => {
    if (!sessionId || !enabled) {
      return;
    }
    const factory =
      eventSourceFactory ??
      (typeof EventSource !== "undefined" ? (url: string) => new EventSource(url) : null);
    if (!factory) {
      return;
    }

    const url = `${API_BASE}${backendPath(sourceFilesPaths.uploadSessionEvents(sessionId))}`;
    const source = factory(url);

    const handle = (message: MessageEvent) => {
      let parsed: SourceUploadProgressEvent;
      try {
        parsed = JSON.parse(message.data) as SourceUploadProgressEvent;
      } catch {
        return; // ignore malformed frames
      }
      setEventState({ enabled, event: parsed, sessionId });
      if (isTerminalUploadState(parsed.state)) {
        source.close();
        onTerminalRef.current?.();
      }
    };

    source.addEventListener("source_upload.progress", handle as EventListener);
    source.onerror = () => {
      // Stream dropped/ended; close and let the caller's polling take over.
      source.close();
    };

    return () => {
      source.removeEventListener("source_upload.progress", handle as EventListener);
      source.close();
    };
  }, [sessionId, enabled, eventSourceFactory]);

  return stateIsStale || !enabled ? null : eventState.event;
}
