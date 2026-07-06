import { cn } from "@/lib/utils";

/**
 * 위저드 단계 표시 (기존 ol.wizard-steps 마크업/클래스 유지 + aria-current 보강).
 */
export function WizardSteps({
  steps,
  current,
  className
}: {
  steps: string[];
  /** 0-based 현재 단계. */
  current: number;
  className?: string;
}) {
  return (
    <ol className={cn("wizard-steps", className)}>
      {steps.map((step, index) => (
        <li
          key={step}
          className={cn(index === current && "active")}
          aria-current={index === current ? "step" : undefined}
        >
          {step}
        </li>
      ))}
    </ol>
  );
}
