import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UploadTab } from "@/components/admin/source-files/UploadTab";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MAX_LIVE_UPLOAD_STREAMS, type UploadSessionStatus } from "@/lib/source-files";

/**
 * Issue #512 regression guard.
 *
 * The pure selector is unit-tested in `source-files.test.ts`; this file pins the thing that
 * actually caused the outage — how many `EventSource`s the *component* opens. A correct
 * selector with the `enabled` prop dropped would keep those tests green while the console
 * froze again, so this test counts real EventSource constructions.
 */

const apiMocks = vi.hoisted(() => ({
  postJson: vi.fn(),
  requestJson: vi.fn()
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, postJson: apiMocks.postJson, requestJson: apiMocks.requestJson };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null;
  closed = false;
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(): void {}
  removeEventListener(): void {}
  close(): void {
    this.closed = true;
  }
}

function session(id: string, updatedAt: string): UploadSessionStatus {
  return {
    upload_session_id: id,
    category: "roadname_hangul_full",
    user_yyyymm: "202603",
    state: "uploading",
    registration_state: "not_registered",
    group_kind: "single_file",
    uploaded_file_count: 0,
    expected_file_count: 1,
    max_bytes: 0,
    part_size_bytes: 0,
    file_slots: [],
    source_file_group_id: `g-${id}`,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: updatedAt,
    display_name: id,
    storage_kind: "rustfs",
    upload_strategy: "multipart"
  } as unknown as UploadSessionStatus;
}

// 6 resumable sessions == the browser's per-origin connection budget: pre-fix this opened 6
// streams and starved every other request on the page.
const SESSIONS = Array.from({ length: 6 }, (_, i) =>
  session(`s${i + 1}`, `2026-06-0${i + 1}T00:00:00Z`)
);

function renderUploadTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } }
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <UploadTab />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("UploadTab live SSE stream cap (#512)", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    apiMocks.requestJson.mockImplementation((path: string) => {
      if (path.includes("categories")) {
        return Promise.resolve({ categories: [] });
      }
      if (path.includes("upload-sessions")) {
        return Promise.resolve(SESSIONS);
      }
      return Promise.resolve([]);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("재개 가능 세션이 6건이어도 EventSource는 상한 개수만 연다", async () => {
    renderUploadTab();
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(0));
    // Give React a chance to over-subscribe if the cap were broken.
    await new Promise((resolve) => setTimeout(resolve, 50));

    const open = FakeEventSource.instances.filter((source) => !source.closed);
    expect(open.length).toBe(MAX_LIVE_UPLOAD_STREAMS);
    // …and they are the most recently updated sessions (s6, s5), not the first rows.
    const ids = open.map((source) => source.url.split("/upload-sessions/")[1]?.split("/")[0]);
    expect(ids.sort()).toEqual(["s5", "s6"]);
  });

  it("무관한 리렌더가 열린 스트림을 재개폐하지 않는다", async () => {
    const { rerender } = renderUploadTab();
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(MAX_LIVE_UPLOAD_STREAMS));
    const before = FakeEventSource.instances.length;

    // A parent re-render with identical data must not tear the streams down: VirtualTable
    // used to rebuild cell closures as new element types, remounting every cell subtree.
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchInterval: false } }
    });
    rerender(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <UploadTab />
        </TooltipProvider>
      </QueryClientProvider>
    );
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(FakeEventSource.instances.length).toBe(before);
    expect(FakeEventSource.instances.filter((s) => !s.closed).length).toBe(
      MAX_LIVE_UPLOAD_STREAMS
    );
  });
});
