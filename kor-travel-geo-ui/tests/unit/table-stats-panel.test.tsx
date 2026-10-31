import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TableStatsPanel } from "@/components/admin/TableStatsPanel";
import { TooltipProvider } from "@/components/ui/tooltip";

const apiMocks = vi.hoisted(() => ({ requestJson: vi.fn() }));

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  requestJson: apiMocks.requestJson
}));

describe("통계 행 수의 추정 표시", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([false, true, undefined])("분석 이력 플래그 %s도 확정 건수로 표시하지 않는다", async (flag) => {
    apiMocks.requestJson.mockResolvedValue([
      {
        table_name: "tl_juso_text",
        row_count: 6_424_765,
        row_count_estimated: flag,
        size_bytes: 1000,
        updated_at: "2026-10-31 10:00:00+00"
      }
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <TableStatsPanel />
        </TooltipProvider>
      </QueryClientProvider>
    );
    const row = await screen.findByRole("row", { name: /tl_juso_text/ });
    expect(row).toHaveTextContent("6,424,765");
    expect(row).toHaveTextContent("추정치");
    expect(screen.getByRole("columnheader", { name: "통계 갱신" })).toBeVisible();
    expect(screen.getByText(/통계 갱신 시각은 적재 완료 시각이 아닙니다/)).toBeVisible();
  });
});
