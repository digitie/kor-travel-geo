"use client";

import { useId, useMemo } from "react";

import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { isValidYyyymm, recentYyyymmOptions } from "@/lib/source-files";

/**
 * 기준년월(YYYYMM) 표준 입력. 숫자만 6자리, 월 01-12 검증, 최근 개월 datalist로
 * 입력을 보조한다. placeholder "예: 202606"은 spec 계약이라 유지한다.
 */
export function YyyymmField({
  id,
  label = "기준년월",
  value,
  onChange,
  help,
  disabled
}: {
  id: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  /** 라벨 옆 도움말 내용 (API 필드명 등). */
  help?: React.ReactNode;
  disabled?: boolean;
}) {
  const listId = useId();
  const options = useMemo(() => recentYyyymmOptions(24), []);
  const invalid = value.length > 0 && !isValidYyyymm(value);

  return (
    <Field data-invalid={invalid || undefined}>
      {/* HelpTip은 label 밖 형제로 둔다 — label 내부 버튼은 RTL getByLabelText가
          다중 컨트롤로 인식한다. */}
      <span className="flex items-center gap-1">
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        {help ? <HelpTip label={`${label} 도움말`}>{help}</HelpTip> : null}
      </span>
      <Input
        id={id}
        inputMode="numeric"
        maxLength={6}
        placeholder="예: 202606"
        list={listId}
        value={value}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        onChange={(event) => onChange(event.target.value.replace(/[^\d]/g, ""))}
      />
      <datalist id={listId}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
      {invalid ? (
        <FieldError>기준년월은 YYYYMM 형식입니다 (예: 202605).</FieldError>
      ) : null}
    </Field>
  );
}
