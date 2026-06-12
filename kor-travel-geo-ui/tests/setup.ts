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
