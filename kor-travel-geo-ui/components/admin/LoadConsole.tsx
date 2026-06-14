"use client";

import { ArrowRight } from "lucide-react";
import { DocumentNavLink } from "@/components/layout/DocumentNavLink";
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
    <Panel title="Source Upload">
      <div className="form-grid">
        <p className="form-note">
          카테고리별 명시적 업로드, 파일 목록, 매칭 세트, RustFS 정합성, 현재 구성은
          전용 화면으로 이동했습니다.
        </p>
        <DocumentNavLink className="button" href="/admin/source-files">
          Source Files 화면으로 이동
          <ArrowRight size={16} />
        </DocumentNavLink>
        <p className="form-note">
          MV refresh / 적재 작업은 Jobs 화면 또는 ktgctl CLI를 사용하세요.
        </p>
      </div>
    </Panel>
  );
}
