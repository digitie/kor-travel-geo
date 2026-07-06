import fs from "node:fs";
import path from "node:path";

import { request as playwrightRequest } from "@playwright/test";

// Admin 인증(fail-closed middleware) 뒤에 있는 mock e2e를 위해 로그인 세션을
// storageState로 저장한다. PLAYWRIGHT_MOCK_LOGIN=1일 때만 활성 —
// live 스위트(tests/e2e/live)는 자체 login 헬퍼를 사용하므로 이 설정 없이 돈다.
export const MOCK_AUTH_STATE_PATH = "test-results/mock-auth/state.json";

export default async function globalSetup() {
  if (process.env.PLAYWRIGHT_MOCK_LOGIN !== "1") return;

  const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:12505";
  const username = process.env.KTG_LIVE_E2E_ADMIN_USERNAME ?? "admin";
  const password = process.env.KTG_LIVE_E2E_ADMIN_PASSWORD;
  if (!password) {
    throw new Error(
      "PLAYWRIGHT_MOCK_LOGIN=1 requires KTG_LIVE_E2E_ADMIN_PASSWORD (server-side KTG_UI_* env must match)"
    );
  }

  const context = await playwrightRequest.newContext({ baseURL });
  const response = await context.post("/api/auth/login", { data: { username, password } });
  if (!response.ok()) {
    throw new Error(`mock-auth login failed: ${response.status()} ${await response.text()}`);
  }
  fs.mkdirSync(path.dirname(MOCK_AUTH_STATE_PATH), { recursive: true });
  await context.storageState({ path: MOCK_AUTH_STATE_PATH });
  await context.dispose();
}
