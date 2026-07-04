"use client";

import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { HelpTip } from "@/components/admin/shared/HelpTip";

/**
 * 정수 범위 입력 표준 (BackupsPanel NumberField 승격판).
 * 빈 입력은 null로 보존하고(0으로 강제 변환 금지), blur 시 min/max로 클램프한다.
 */
export function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
  help,
  description,
  disabled
}: {
  id: string;
  label: React.ReactNode;
  value: number | null;
  onChange: (value: number | null) => void;
  min: number;
  max: number;
  step?: number;
  /** 값 뒤 단위 표기 (예: "일", "개"). */
  suffix?: string;
  help?: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <Field>
      {/* HelpTip은 label 밖 형제로 둔다 — label 내부 버튼은 RTL getByLabelText가
          다중 컨트롤로 인식한다. */}
      <span className="flex items-center gap-1">
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        {help ? <HelpTip>{help}</HelpTip> : null}
      </span>
      <span className="flex items-center gap-2">
        <Input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          step={step}
          value={value ?? ""}
          disabled={disabled}
          onChange={(event) => {
            const raw = event.target.value;
            if (raw === "") {
              onChange(null);
              return;
            }
            const parsed = Number(raw);
            onChange(Number.isNaN(parsed) ? null : parsed);
          }}
          onBlur={() => {
            if (value == null) return;
            const clamped = Math.min(max, Math.max(min, Math.round(value)));
            if (clamped !== value) onChange(clamped);
          }}
        />
        {suffix ? (
          <span className="shrink-0 text-sm text-muted-foreground">{suffix}</span>
        ) : null}
      </span>
      {description ? <FieldDescription>{description}</FieldDescription> : null}
    </Field>
  );
}
