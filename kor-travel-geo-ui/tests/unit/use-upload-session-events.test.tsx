import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useUploadSessionEvents } from "@/lib/use-upload-session-events";

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  url: string;
  closed = false;
  onerror: (() => void) | null = null;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(type: string, cb: Listener): void {
    (this.listeners[type] ??= []).push(cb);
  }

  removeEventListener(type: string, cb: Listener): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== cb);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: string): void {
    for (const cb of this.listeners[type] ?? []) {
      cb({ data } as MessageEvent);
    }
  }
}

function progress(state: string, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    event: "source_upload.progress",
    upload_session_id: "sess1",
    state,
    ...extra
  });
}

describe("useUploadSessionEvents", () => {
  it("streams source_upload.progress and closes on a terminal state", () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => {
      created = new FakeEventSource(url);
      return created as unknown as EventSource;
    };
    const onTerminal = vi.fn();
    const { result } = renderHook(() =>
      useUploadSessionEvents("sess1", { eventSourceFactory: factory, onTerminal })
    );

    expect(result.current).toBeNull();
    expect(created).not.toBeNull();
    expect(created!.url).toContain("/admin/source-files/upload-sessions/sess1/events");

    act(() => created!.emit("source_upload.progress", progress("uploading", { progress: 0.4, stage: "parts" })));
    expect(result.current?.state).toBe("uploading");
    expect(result.current?.progress).toBe(0.4);
    expect(onTerminal).not.toHaveBeenCalled();
    expect(created!.closed).toBe(false);

    act(() => created!.emit("source_upload.progress", progress("registered")));
    expect(result.current?.state).toBe("registered");
    expect(created!.closed).toBe(true);
    expect(onTerminal).toHaveBeenCalledTimes(1);
  });

  it("ignores malformed frames", () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => {
      created = new FakeEventSource(url);
      return created as unknown as EventSource;
    };
    const { result } = renderHook(() =>
      useUploadSessionEvents("sess1", { eventSourceFactory: factory })
    );
    act(() => created!.emit("source_upload.progress", "not-json"));
    expect(result.current).toBeNull();
  });

  it("no-ops when disabled or sessionId is null", () => {
    const factory = vi.fn();
    renderHook(() => useUploadSessionEvents(null, { eventSourceFactory: factory }));
    renderHook(() => useUploadSessionEvents("s", { enabled: false, eventSourceFactory: factory }));
    expect(factory).not.toHaveBeenCalled();
  });
});
