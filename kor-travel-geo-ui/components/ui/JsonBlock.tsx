"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * JSON pretty 덤프 (pre.json-box는 e2e CSS 셀렉터 계약이라 유지) + 복사 버튼.
 * clipboard API가 없는 환경(http LAN 등)에서는 pre 내용 전체 선택으로 폴백한다.
 */
export function JsonBlock({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
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
      // clipboard 불가(비보안 컨텍스트/권한 거부) — 내용을 전체 선택해 수동 복사를 돕는다.
      const node = preRef.current;
      if (node) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
    }
  }

  return (
    <div className="group relative min-w-0">
      <pre className="json-box" ref={preRef}>
        {text}
      </pre>
      <button
        type="button"
        aria-label="JSON 복사"
        onClick={() => void copy()}
        className="absolute top-2 right-2 inline-flex size-8 items-center justify-center rounded-md bg-white/10 text-white/70 opacity-0 transition-opacity duration-[var(--duration-fast)] outline-none group-hover:opacity-100 hover:bg-white/20 hover:text-white focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}
