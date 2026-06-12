"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo } from "react";

const STORAGE_KEY = "kortravelgeo.vworldApiKey";
const RUNTIME_KEY_QUERY_KEY = ["runtime-config", "vworld-api-key"] as const;

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
    const payload = (await response.json()) as { vworldApiKey?: unknown };
    envApiKey = typeof payload.vworldApiKey === "string" ? payload.vworldApiKey.trim() : "";
  } catch {
    envApiKey = "";
  }

  const browserKey =
    typeof window === "undefined" ? "" : window.localStorage.getItem(STORAGE_KEY)?.trim() ?? "";

  return { browserKey, envApiKey };
}

export function VWorldKeyProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const { data: runtimeKey, isLoading } = useQuery({
    queryKey: RUNTIME_KEY_QUERY_KEY,
    queryFn: loadRuntimeKey,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false
  });

  const envApiKey = runtimeKey?.envApiKey ?? "";
  const browserKey = runtimeKey?.browserKey ?? "";
  const apiKey = browserKey || envApiKey;
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
    if (trimmed) {
      window.localStorage.setItem(STORAGE_KEY, trimmed);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    queryClient.setQueryData<RuntimeKeyRecord>(RUNTIME_KEY_QUERY_KEY, (current) => ({
      browserKey: trimmed,
      envApiKey: current?.envApiKey ?? envApiKey
    }));
  }, [envApiKey, queryClient]);

  const resetApiKey = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
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
