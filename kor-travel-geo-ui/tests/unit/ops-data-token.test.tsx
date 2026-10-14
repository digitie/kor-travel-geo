import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OpsPanel } from "@/components/admin/OpsPanel";
import type { ServingRelease } from "@/lib/api";
const mocks = vi.hoisted(() => ({ requestJson: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), requestJson: mocks.requestJson }));
const token = "dd1-" + "a".repeat(32);
const old: ServingRelease = { serving_release_id: "old", dataset_snapshot_id: "s0", state: "superseded", release_kind: "full_load", mv_name: "mv", created_at: "2026-10-13T00:00:00Z", activated_at: "2026-10-13T01:00:00Z", data_token: token };
const active: ServingRelease = { ...old, serving_release_id: "active", state: "active", previous_serving_release_id: "old" };
function rows(releases: ServingRelease[]) {
  mocks.requestJson.mockImplementation(async (path: string) => path.includes("/ops/releases") ? releases : []);
}
beforeEach(() => { mocks.requestJson.mockReset(); });
afterEach(cleanup);
it("실제 ops 표는 지문 열과 이전 릴리스 데이터 동일 배지를 표시한다", async () => {
  rows([active, old]);render(<OpsPanel />);
  const table = await screen.findByRole("table", { name: "서빙 릴리스 목록" });
  await within(table).findByText("데이터 동일");expect(within(table).getByText("data_token")).toBeTruthy();
});
it("실제 이전 활성화 두 건의 지문 누락을 경고하고 도움말을 제공한다", async () => {
  rows([{ ...active, data_token: null, notes: "data_fingerprint_failed: timeout" }, { ...old, data_token: null }]);
  render(<OpsPanel />);await screen.findByText("최근 두 활성 릴리스의 데이터 지문이 없습니다");
  expect(screen.getAllByText("지문 없음")).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "데이터 지문 없음 도움말" })).toHaveLength(2);
});
it("조회에 실제 이전 릴리스가 없으면 무관한 누락 행으로 연속 경고를 만들지 않는다", async () => {
  rows([{ ...active, data_token: null }, { ...old, serving_release_id: "unrelated", data_token: null }]);
  render(<OpsPanel />);await screen.findAllByText("지문 없음");
  expect(screen.queryByText("최근 두 활성 릴리스의 데이터 지문이 없습니다")).toBeNull();
});
