"use client";

import { ArrowRight } from "lucide-react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";

/**
 * T-201 removed the legacy auto-detection upload-SET surface
 * (`/admin/uploads*`, `/admin/load-sources/*`) that this console drove.
 *
 * T-209 added the replacement explicit per-category source-file upload UI at
 * `/admin/source-files`. This stub now points operators to that page (upload /
 * list / match sets / reconcile / current config) instead of duplicating it.
 */
export function LoadConsole() {
  return (
    <Panel title="적재 화면 안내">
      <div className="form-grid">
        <p className="form-note">적재 파일 관리는 원천 파일 화면으로 이동했습니다.</p>
        <Button asChild className="justify-self-start">
          <DocumentNavLink href="/admin/source-files">
            원천 파일 화면으로 이동
            <ArrowRight aria-hidden="true" size={16} />
          </DocumentNavLink>
        </Button>
        <p className="form-note">
          MV refresh·적재 작업은 백업/복원 화면의 작업 탭에서 확인합니다.
          <HelpTip label="적재 작업 도움말">
            서버에서는 <code>ktgctl</code> CLI로 같은 작업을 실행할 수 있습니다.
          </HelpTip>
        </p>
        <Button asChild className="justify-self-start" variant="outline">
          <DocumentNavLink href="/admin/backups">
            백업/복원 화면으로 이동
            <ArrowRight aria-hidden="true" size={16} />
          </DocumentNavLink>
        </Button>
      </div>
    </Panel>
  );
}
