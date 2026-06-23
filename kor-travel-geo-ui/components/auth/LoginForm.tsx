"use client";

import { LockKeyhole, LogIn } from "lucide-react";
import { FormEvent, useState } from "react";

export function LoginForm({ nextPath }: { nextPath: string }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password, next: nextPath })
      });
      if (response.status === 503) {
        setError("로그인 환경변수가 설정되지 않았습니다.");
        return;
      }
      if (response.status === 429) {
        setError("로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.");
        return;
      }
      if (response.status === 403) {
        setError("허용되지 않은 요청입니다. 로그인 화면을 새로고침하세요.");
        return;
      }
      if (!response.ok) {
        setError("아이디 또는 비밀번호가 올바르지 않습니다.");
        return;
      }
      const payload = (await response.json()) as { next?: string };
      window.location.assign(payload.next ?? nextPath);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="login-shell" aria-labelledby="login-title">
      <div className="login-panel">
        <div className="login-brand">
          <div className="login-icon" aria-hidden="true">
            <LockKeyhole size={24} />
          </div>
          <div>
            <p>kor-travel-geo-ui</p>
            <h1 id="login-title">관리자 로그인</h1>
          </div>
        </div>
        <form className="login-form" onSubmit={submit} aria-busy={busy}>
          <div className="field">
            <label htmlFor="admin-username">아이디</label>
            <input
              autoComplete="username"
              id="admin-username"
              value={username}
              disabled={busy}
              aria-describedby="login-error"
              aria-invalid={error ? true : undefined}
              onChange={(event) => setUsername(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="admin-password">비밀번호</label>
            <input
              autoComplete="current-password"
              id="admin-password"
              type="password"
              value={password}
              disabled={busy}
              aria-describedby="login-error"
              aria-invalid={error ? true : undefined}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <button className="button login-submit" disabled={busy} type="submit">
            <LogIn size={17} />
            로그인
          </button>
          {/* Always-present assertive live region so a failed-login message is announced to AT. */}
          <p className="login-error" id="login-error" role="alert" aria-live="assertive">
            {error}
          </p>
        </form>
      </div>
    </section>
  );
}
