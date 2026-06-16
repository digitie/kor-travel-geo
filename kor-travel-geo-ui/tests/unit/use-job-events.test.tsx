import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useJobEvents } from "@/lib/use-job-events";

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

function status(state: string, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({ job_id: "job-1", kind: "db_backup", state, progress: 0, ...extra });
}

describe("useJobEvents (T-251)", () => {
  it("streams status frames and closes on a terminal state", () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => {
      created = new FakeEventSource(url);
      return created as unknown as EventSource;
    };
    const onTerminal = vi.fn();
    const { result } = renderHook(() =>
      useJobEvents("job-1", { eventSourceFactory: factory, onTerminal })
    );

    expect(result.current).toBeNull();
    expect(created).not.toBeNull();
    expect(created!.url).toContain("/admin/jobs/job-1/events");

    act(() => created!.emit("status", status("running", { progress: 0.4, current_stage: "dump" })));
    expect(result.current?.state).toBe("running");
    expect(result.current?.progress).toBe(0.4);
    expect(onTerminal).not.toHaveBeenCalled();
    expect(created!.closed).toBe(false);

    act(() => created!.emit("status", status("done", { progress: 1 })));
    expect(result.current?.state).toBe("done");
    expect(created!.closed).toBe(true);
    expect(onTerminal).toHaveBeenCalledTimes(1);
  });

  it("does not open a stream when disabled", () => {
    const factory = vi.fn();
    const { result } = renderHook(() =>
      useJobEvents("job-1", { enabled: false, eventSourceFactory: factory as never })
    );
    expect(result.current).toBeNull();
    expect(factory).not.toHaveBeenCalled();
  });
});
