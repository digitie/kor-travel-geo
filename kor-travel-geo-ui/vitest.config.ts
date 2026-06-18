import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const appRoot = new URL(".", import.meta.url).pathname;
const vworldPackagesRoot = new URL("./node_modules/maplibre-vworld-react/packages/", import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/unit/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"]
  },
  resolve: {
    alias: {
      "@": appRoot,
      "vworld-map-core": `${vworldPackagesRoot}vworld-map-core/src`,
      "vworld-map-web": `${vworldPackagesRoot}vworld-map-web/src`
    }
  }
});
