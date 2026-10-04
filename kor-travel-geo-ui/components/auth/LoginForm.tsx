"use client";

import { LoginForm as CommonLoginForm, type LoginSubmission } from "@kor-travel/ui/login-form";
import { sanitizeLocalPath } from "@kor-travel/ui/navigation";
import { useState } from "react";

export function LoginForm({ nextPath }: { nextPath: string }) {
  const [error, setError] = useState<string | null>(null);
  async function submit({ credentials, nextPath: safeNext }: LoginSubmission) {
    const response = await fetch("/api/auth/login", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...credentials, next: safeNext }), signal: AbortSignal.timeout(25_000)
    });
    if (!response.ok) {
      setError(response.status === 503 ? "로그인 환경변수가 설정되지 않았습니다."
        : response.status === 429 ? "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
        : response.status === 403 ? "허용되지 않은 요청입니다. 로그인 화면을 새로고침하세요."
        : "아이디 또는 비밀번호가 올바르지 않습니다.");
      return;
    }
    const payload = await response.json() as { next?: string };
    window.location.assign(sanitizeLocalPath(payload.next ?? safeNext));
  }
  return <section className="login-shell"><div className="login-panel">
    <CommonLoginForm brand="Geocoder Admin UI" description="관리자 계정으로 로그인해 주세요."
      defaultUsername="admin" nextPath={nextPath} onSubmit={submit} error={error}
      onClearError={() => setError(null)} />
  </div></section>;
}
