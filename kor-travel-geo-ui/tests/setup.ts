import "@testing-library/jest-dom/vitest";
import { createRequire } from "node:module";

const requireShim = createRequire(import.meta.url);

if (!("require" in globalThis)) {
  Object.defineProperty(globalThis, "require", {
    configurable: true,
    value: requireShim
  });
}

if (!window.URL.createObjectURL) {
  Object.defineProperty(window.URL, "createObjectURL", {
    configurable: true,
    value: () => "blob:maplibre-worker"
  });
}

if (!window.URL.revokeObjectURL) {
  Object.defineProperty(window.URL, "revokeObjectURL", {
    configurable: true,
    value: () => undefined
  });
}

// In some Windows/Node runtimes the experimental Node `localStorage` shadows the
// jsdom one and lacks the Web Storage methods (getItem/setItem/clear), so tests
// that touch window.localStorage throw `is not a function`. Install a minimal
// in-memory Storage when the methods are missing.
if (typeof window.localStorage?.setItem !== "function") {
  const store = new Map<string, string>();
  const memoryStorage: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    }
  };
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: memoryStorage
  });
}
