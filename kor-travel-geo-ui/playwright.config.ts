import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:12505";
// 관리 UI가 fail-closed 인증 뒤에 있으므로 mock 스위트는 PLAYWRIGHT_MOCK_LOGIN=1로
// 로그인 세션(storageState)을 공유받아야 한다 (tests/e2e/mock-auth-setup.ts).
const mockLogin = process.env.PLAYWRIGHT_MOCK_LOGIN === "1";
const allProjects = [
  {
    name: "chromium",
    use: { ...devices["Desktop Chrome"] }
  },
  {
    name: "firefox",
    use: { ...devices["Desktop Firefox"] }
  }
];
const selectedBrowser = process.env.PLAYWRIGHT_BROWSER;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  globalSetup: mockLogin ? "./tests/e2e/mock-auth-setup.ts" : undefined,
  use: {
    baseURL,
    trace: "on-first-retry",
    ...(mockLogin ? { storageState: "test-results/mock-auth/state.json" } : {})
  },
  projects: selectedBrowser
    ? allProjects.filter((project) => project.name === selectedBrowser)
    : allProjects
});
