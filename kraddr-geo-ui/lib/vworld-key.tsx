"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "kraddr.geo.vworldApiKey";

type VWorldKeySource = "env" | "browser" | "empty" | "loading";

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

export function VWorldKeyProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKey] = useState("");
  const [envApiKey, setEnvApiKey] = useState("");
  const [source, setSource] = useState<VWorldKeySource>("loading");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadRuntimeKey() {
      try {
        const response = await fetch("/api/runtime-config", { cache: "no-store" });
        const payload = (await response.json()) as { vworldApiKey?: unknown };
        const envKey = typeof payload.vworldApiKey === "string" ? payload.vworldApiKey.trim() : "";
        const browserKey = window.localStorage.getItem(STORAGE_KEY)?.trim() ?? "";
        if (!active) return;

        setEnvApiKey(envKey);
        setApiKey(browserKey || envKey);
        setSource(browserKey ? "browser" : envKey ? "env" : "empty");
      } catch {
        const browserKey = window.localStorage.getItem(STORAGE_KEY)?.trim() ?? "";
        if (!active) return;

        setApiKey(browserKey);
        setSource(browserKey ? "browser" : "empty");
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadRuntimeKey();
    return () => {
      active = false;
    };
  }, []);

  const saveApiKey = useCallback((value: string) => {
    const trimmed = value.trim();
    if (trimmed) {
      window.localStorage.setItem(STORAGE_KEY, trimmed);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    setApiKey(trimmed || envApiKey);
    setSource(trimmed ? "browser" : envApiKey ? "env" : "empty");
  }, [envApiKey]);

  const resetApiKey = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setApiKey(envApiKey);
    setSource(envApiKey ? "env" : "empty");
  }, [envApiKey]);

  const value = useMemo(
    () => ({ apiKey, envApiKey, loading, resetApiKey, saveApiKey, source }),
    [apiKey, envApiKey, loading, resetApiKey, saveApiKey, source]
  );

  return <VWorldKeyContext.Provider value={value}>{children}</VWorldKeyContext.Provider>;
}

export function useVWorldApiKey() {
  return useContext(VWorldKeyContext);
}
