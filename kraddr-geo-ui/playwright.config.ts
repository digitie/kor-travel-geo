import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:12205";
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
  use: {
    baseURL,
    trace: "on-first-retry"
  },
  projects: selectedBrowser
    ? allProjects.filter((project) => project.name === selectedBrowser)
    : allProjects
});
