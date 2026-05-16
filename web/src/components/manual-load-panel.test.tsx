import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ManualLoadPanel, formatBytes } from "./manual-load-panel";

const apiBaseUrl = "http://127.0.0.1:3011";

describe("ManualLoadPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("accepts multiple dropped files and starts an upload job with FormData", async () => {
    const onJobComplete = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "job-1",
        dataset: "auto",
        replace: false,
        status: "pending",
        total_files: 2,
        processed_files: 0,
        current_file: "",
        loaded: 0,
        skipped: 0,
        message: "대기 중",
        errors: [],
        progress_percent: 0,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<ManualLoadPanel apiBaseUrl={apiBaseUrl} onJobComplete={onJobComplete} />);

    const dropZone = screen.getByText(/TXT, ZIP, 7Z, SHP/).closest("label");
    expect(dropZone).not.toBeNull();
    fireEvent.drop(dropZone!, {
      dataTransfer: {
        items: [],
        files: [
          new File(["a"], "entrc_seoul.txt", { type: "text/plain" }),
          new File(["b"], "match_build_seoul.txt", { type: "text/plain" }),
        ],
      },
    });

    expect(await screen.findByText(/2개 파일/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "적재 시작" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${apiBaseUrl}/load-jobs`);
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.get("dataset")).toBe("auto");
    expect(form.get("replace")).toBe("false");
    expect(form.getAll("files")).toHaveLength(2);
    expect(await screen.findByText("대기 중")).toBeTruthy();
  });

  it("submits selected files, replace flag, dataset kind, and completion progress", async () => {
    const onJobComplete = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: "job-2",
          dataset: "boundary_shapes",
          replace: true,
          status: "succeeded",
          total_files: 1,
          processed_files: 1,
          current_file: "",
          loaded: 7,
          skipped: 1,
          message: "적재 완료",
          errors: [],
          progress_percent: 100,
        }),
      ),
    );

    render(<ManualLoadPanel apiBaseUrl={apiBaseUrl} onJobComplete={onJobComplete} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(
      input,
      new File(["shape"], "TL_SCCO_SIG.shp", { type: "application/octet-stream" }),
    );
    await userEvent.selectOptions(screen.getByLabelText("자료 유형"), "boundary_shapes");
    await userEvent.click(screen.getByLabelText("같은 자료를 먼저 비우고 적재"));
    await userEvent.click(screen.getByRole("button", { name: "적재 시작" }));

    expect(await screen.findByText("적재 완료")).toBeTruthy();
    expect(screen.getByText("100.0%")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
    await waitFor(() => expect(onJobComplete).toHaveBeenCalledTimes(1));
  });

  it("shows a validation error before upload when no files are selected", async () => {
    render(<ManualLoadPanel apiBaseUrl={apiBaseUrl} onJobComplete={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "적재 시작" }));

    expect(screen.getByText("업로드할 파일을 먼저 선택하세요.")).toBeTruthy();
  });
});

describe("formatBytes", () => {
  it("formats byte counts for the upload file list", () => {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB");
  });
});

function jsonResponse(payload: object) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}
