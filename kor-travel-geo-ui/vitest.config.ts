import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const appRoot = new URL(".", import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // 배포 ESM의 지도 CSS를 Node 대신 Vite에서 처리한다.
    server: { deps: { inline: ["vworld-map-web", "maplibre-gl"] } },
    globals: true,
    include: ["tests/unit/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"]
  },
  resolve: {
    alias: {
      "@": appRoot,
    }
  }
});
