"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo } from "react";
import { usePathname } from "next/navigation";

const RUNTIME_KEY_QUERY_KEY = ["runtime-config", "vworld-api-key"] as const;

// VWorld 키의 UI override는 현재 탭에서만 유지한다. 장기 웹 저장소에 API 키를
// 두지 않아 XSS 노출면을 늘리지 않는다.
let browserOverrideKey = "";

type VWorldKeySource = "env" | "browser" | "empty" | "loading";
type RuntimeKeyRecord = {
  browserKey: string;
  envApiKey: string;
};

type VWorldKeyState = {
  apiKey: string;
  envApiKey: string;
  loading: boolean;
  source: VWorldKeySource;
  resetApiKey: () => void;
  saveApiKey: (value: string) => void;
};

const fallbackState: VWorldKeyState = {
  apiKey: "",
  envApiKey: "",
  loading: false,
  source: "empty",
  resetApiKey: () => undefined,
  saveApiKey: () => undefined
};

const VWorldKeyContext = createContext<VWorldKeyState>(fallbackState);

async function loadRuntimeKey(): Promise<RuntimeKeyRecord> {
  let envApiKey = "";

  try {
    const response = await fetch("/api/runtime-config", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("runtime config request failed");
    }
    const payload = (await response.json()) as { vworldApiKey?: unknown };
    envApiKey = typeof payload.vworldApiKey === "string" ? payload.vworldApiKey.trim() : "";
  } catch {
    envApiKey = "";
  }

  const browserKey = browserOverrideKey;

  return { browserKey, envApiKey };
}

export function VWorldKeyProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  // The provider lives in the root layout, so it also mounts on /login where the caller has no
  // session yet — `/api/runtime-config` answers 401 and the browser logs a console error on
  // every visit (issue #515). There is no map on the login page, so just don't ask.
  const pathname = usePathname();
  const enabled = pathname !== "/login";
  const { data: runtimeKey, isLoading } = useQuery({
    queryKey: RUNTIME_KEY_QUERY_KEY,
    queryFn: loadRuntimeKey,
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false
  });

  const envApiKey = runtimeKey?.envApiKey ?? "";
  const browserKey = runtimeKey?.browserKey ?? "";
  const apiKey = browserKey || envApiKey;
  // react-query v5 reports `isLoading = isPending && isFetching`, so a disabled query is
  // already `isLoading: false` — no extra guard needed on /login.
  const loading = isLoading;
  const source: VWorldKeySource = loading
    ? "loading"
    : browserKey
      ? "browser"
      : envApiKey
        ? "env"
        : "empty";

  const saveApiKey = useCallback((value: string) => {
    const trimmed = value.trim();
    browserOverrideKey = trimmed;
    queryClient.setQueryData<RuntimeKeyRecord>(RUNTIME_KEY_QUERY_KEY, (current) => ({
      browserKey: trimmed,
      envApiKey: current?.envApiKey ?? envApiKey
    }));
  }, [envApiKey, queryClient]);

  const resetApiKey = useCallback(() => {
    browserOverrideKey = "";
    queryClient.setQueryData<RuntimeKeyRecord>(RUNTIME_KEY_QUERY_KEY, (current) => ({
      browserKey: "",
      envApiKey: current?.envApiKey ?? envApiKey
    }));
  }, [envApiKey, queryClient]);

  const value = useMemo(
    () => ({ apiKey, envApiKey, loading, resetApiKey, saveApiKey, source }),
    [apiKey, envApiKey, loading, resetApiKey, saveApiKey, source]
  );

  return <VWorldKeyContext.Provider value={value}>{children}</VWorldKeyContext.Provider>;
}

export function useVWorldApiKey() {
  return useContext(VWorldKeyContext);
}
