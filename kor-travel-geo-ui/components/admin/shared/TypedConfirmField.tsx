"use client";

import { CheckCircle2 } from "lucide-react";
import { useId } from "react";

/**
 * 위험 작업 typed confirmation 공용 필드. 요구 문구를 <code>로 보여주고
 * 정확히 입력해야 통과한다(붙여넣기 마찰은 의도적으로 유지 — 복사 버튼 없음).
 * 기존 계약 유지: .confirm-box 컨테이너, input의 aria-label(호출부가 지정),
 * 불일치 안내 문구 "확인 문구가 일치해야 합니다."
 */
export function TypedConfirmField({
  phrase,
  value,
  onChange,
  label,
  heading = "확인 문구",
  description,
  role
}: {
  /** 요구되는 정확한 확인 문구 (서버 계약 값 그대로). */
  phrase: string;
  value: string;
  onChange: (value: string) => void;
  /** input의 aria-label — 기존 spec 계약 문자열을 그대로 넘긴다. */
  label: string;
  heading?: string;
  description?: React.ReactNode;
  /** 기존 마크업이 role=alert였던 곳(.confirm-box[role=alert] spec)만 지정. */
  role?: "alert";
}) {
  const hintId = useId();
  const matches = value === phrase;

  return (
    <div className="confirm-box" role={role}>
      <p className="confirm-title m-0">{heading}</p>
      {description ? (
        <p className="m-0 text-xs text-muted-foreground">{description}</p>
      ) : null}
      <p className="m-0 text-xs">
        아래 문구를 정확히 입력하세요: <code className="select-all">{phrase}</code>
      </p>
      <input
        aria-label={label}
        aria-describedby={hintId}
        aria-invalid={value.length > 0 && !matches ? true : undefined}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <p id={hintId} className="m-0 flex items-center gap-1 text-xs" aria-live="polite">
        {matches ? (
          <span className="inline-flex items-center gap-1 font-semibold text-[var(--ok)]">
            <CheckCircle2 className="size-3.5" aria-hidden="true" /> 확인 문구가 일치합니다.
          </span>
        ) : (
          <span className="text-muted-foreground">확인 문구가 일치해야 합니다.</span>
        )}
      </p>
    </div>
  );
}
