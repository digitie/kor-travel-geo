"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * JSON pretty 덤프 (pre.json-box는 e2e CSS 셀렉터 계약이라 유지) + 복사 버튼.
 * clipboard API가 없는 환경(http LAN 등)에서는 복사 버튼을 숨긴다.
 */
export function JsonBlock({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  const [copied, setCopied] = useState(false);
  const [canCopy, setCanCopy] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setCanCopy(typeof navigator !== "undefined" && Boolean(navigator.clipboard));
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (resetTimer.current) clearTimeout(resetTimer.current);
      resetTimer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard 거부 시 조용히 무시 — pre 내용을 직접 선택해 복사할 수 있다.
    }
  }

  return (
    <div className="group relative min-w-0">
      <pre className="json-box">{text}</pre>
      {canCopy ? (
        <button
          type="button"
          aria-label="JSON 복사"
          onClick={() => void copy()}
          className="absolute top-2 right-2 inline-flex size-8 items-center justify-center rounded-md bg-white/10 text-white/70 opacity-0 transition-opacity duration-[var(--duration-fast)] outline-none group-hover:opacity-100 hover:bg-white/20 hover:text-white focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </button>
      ) : null}
    </div>
  );
}
