"use client";

import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { DbLifecycleCapabilities } from "@/lib/api";
import { DB_LIFECYCLE_UNSUPPORTED_TEXT, dbLifecycleBlocked } from "@/lib/backup-workflow";

/** T-312: 공용 DB instance에서 막힌 기능 앞에 붙이는 짧은 안내. 지원되면 아무것도 그리지 않는다. */
export function DbLifecycleNotice({
  capabilities,
  feature
}: {
  capabilities: DbLifecycleCapabilities | null | undefined;
  feature: string;
}) {
  if (!dbLifecycleBlocked(capabilities)) return null;
  return (
    <Alert role="status" variant="warning">
      <AlertTriangle aria-hidden="true" />
      <AlertDescription>
        <p>
          {feature}: {DB_LIFECYCLE_UNSUPPORTED_TEXT}
        </p>
        {capabilities.reason ? (
          <p className="text-xs text-muted-foreground">{capabilities.reason}</p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
