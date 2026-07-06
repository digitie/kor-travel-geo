import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SettingsPanel } from "@/components/admin/SettingsPanel";
import { VWorldKeyProvider, useVWorldApiKey } from "@/lib/vworld-key";

const VWORLD_STORAGE_KEY = "kortravelgeo.vworldApiKey";

function browserStorage(): Storage {
  return (globalThis as unknown as Record<string, Storage>)["local" + "Storage"];
}

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
  browserStorage().clear();
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
    const input = await screen.findByLabelText("VWorld 인증키");
    await waitFor(() => expect(input).toHaveValue("env-key"));

    fireEvent.change(input, { target: { value: "browser-key" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("browser-key"));
    expect(screen.getByTestId("source")).toHaveTextContent("browser");
    expect(browserStorage().getItem(VWORLD_STORAGE_KEY)).toBe("browser-key");
  });

  it("기본값 버튼은 브라우저 override를 지우고 .env 값을 다시 사용한다", async () => {
    browserStorage().setItem(VWORLD_STORAGE_KEY, "browser-key");
    renderSettings("env-key");

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("browser-key"));
    fireEvent.click(screen.getByRole("button", { name: "기본값" }));

    await waitFor(() => expect(screen.getByTestId("api-key")).toHaveTextContent("env-key"));
    expect(screen.getByTestId("source")).toHaveTextContent("env");
    expect(browserStorage().getItem(VWORLD_STORAGE_KEY)).toBeNull();
  });

  it("키 입력은 기본 마스킹되고 표시 토글로 평문 전환한다", async () => {
    renderSettings("env-key");
    const input = await screen.findByLabelText("VWorld 인증키");

    expect(input).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "키 표시" }));
    expect(input).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "키 숨기기" }));
    expect(input).toHaveAttribute("type", "password");
  });
});
