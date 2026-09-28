import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CachePanel } from "@/components/admin/CachePanel";

const apiMocks = vi.hoisted(() => ({
  requestJson: vi.fn()
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, requestJson: apiMocks.requestJson };
});

describe("CachePanel (T-310)", () => {
  beforeEach(() => {
    apiMocks.requestJson.mockReset();
  });

  it("loads the scan-free estimate by default and counts exactly only on request", async () => {
    apiMocks.requestJson
      .mockResolvedValueOnce({ enabled: true, entries: 120, hits: 7, expired: 0, exact: false })
      .mockResolvedValueOnce({ enabled: true, entries: 118, hits: 3, expired: 1, exact: true });

    render(<CachePanel />);

    expect(await screen.findByText("추정치")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(apiMocks.requestJson).toHaveBeenCalledTimes(1);
    expect(apiMocks.requestJson).toHaveBeenLastCalledWith("/admin/cache/metrics");

    fireEvent.click(screen.getByRole("button", { name: "정확히 세기" }));

    expect(await screen.findByText("정확 집계")).toBeInTheDocument();
    expect(screen.getByText("118")).toBeInTheDocument();
    expect(apiMocks.requestJson).toHaveBeenCalledTimes(2);
    expect(apiMocks.requestJson).toHaveBeenLastCalledWith("/admin/cache/metrics?exact=true");
  });

  it("goes back to the estimate on refresh", async () => {
    apiMocks.requestJson
      .mockResolvedValueOnce({ enabled: true, entries: 5, hits: 0, expired: 0, exact: true })
      .mockResolvedValueOnce({ enabled: true, entries: 6, hits: 0, expired: 0, exact: false });

    render(<CachePanel />);
    expect(await screen.findByText("정확 집계")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));

    expect(await screen.findByText("추정치")).toBeInTheDocument();
    expect(apiMocks.requestJson).toHaveBeenLastCalledWith("/admin/cache/metrics");
  });
});
