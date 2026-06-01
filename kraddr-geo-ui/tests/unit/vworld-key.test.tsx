import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsPanel } from "@/components/admin/SettingsPanel";
import { VWorldKeyProvider, useVWorldApiKey } from "@/lib/vworld-key";

function KeyProbe() {
  const { apiKey, source } = useVWorldApiKey();
  return (
    <div>
      <span data-testid="api-key">{apiKey}</span>
      <span data-testid="source">{source}</span>
    </div>
  );
}

function renderSettings(envKey = "env-key") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      json: async () => ({ vworldApiKey: envKey })
    }))
  );

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false
      }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <VWorldKeyProvider>
        <SettingsPanel />
        <KeyProbe />
      </VWorldKeyProvider>
    </QueryClientProvider>
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("VWorld key settings", () => {
  it(".env 런타임 기본값을 지도 키로 사용한다", async () => {
    renderSettings("env-key");

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("env-key"));
    expect(screen.getByTestId("source")).toHaveTextContent("env");
    expect(screen.getAllByText(".env 기본값").length).toBeGreaterThan(0);
  });

  it("UI 입력값을 저장하면 브라우저 override를 사용한다", async () => {
    renderSettings("env-key");
    const input = await screen.findByLabelText("NEXT_PUBLIC_VWORLD_API_KEY");
    await waitFor(() => expect(input).toHaveValue("env-key"));

    fireEvent.change(input, { target: { value: "browser-key" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("browser-key"));
    expect(screen.getByTestId("source")).toHaveTextContent("browser");
    expect(window.localStorage.getItem("kraddr.geo.vworldApiKey")).toBe("browser-key");
  });

  it("기본값 버튼은 브라우저 override를 지우고 .env 값을 다시 사용한다", async () => {
    window.localStorage.setItem("kraddr.geo.vworldApiKey", "browser-key");
    renderSettings("env-key");

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("browser-key"));
    fireEvent.click(screen.getByRole("button", { name: "기본값" }));

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("env-key"));
    expect(screen.getByTestId("source")).toHaveTextContent("env");
    expect(window.localStorage.getItem("kraddr.geo.vworldApiKey")).toBeNull();
  });
});
