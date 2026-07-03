import { AlertTriangle, XCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

/**
 * blocker/warning 목록 표준 표기 (HotSwap/RestoreWizard/Reconcile 공통 패턴).
 * 기존 .wizard-list.blocker/.warn 클래스를 관성 훅으로 유지한다.
 */
export function IssueList({
  tone,
  title,
  items,
  className
}: {
  tone: "error" | "warn";
  title: React.ReactNode;
  items: React.ReactNode[];
  className?: string;
}) {
  if (!items.length) return null;
  const Icon = tone === "error" ? XCircle : AlertTriangle;
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "warning"}
      role={tone === "error" ? "alert" : undefined}
      className={cn("wizard-list", tone === "error" ? "blocker" : "warn", className)}
    >
      <Icon aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <ul className="m-0 list-disc pl-4">
          {items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
