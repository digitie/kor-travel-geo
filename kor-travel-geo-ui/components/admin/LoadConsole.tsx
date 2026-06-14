"use client";

import { Panel } from "@/components/ui/Panel";

/**
 * T-201 removed the legacy auto-detection upload-SET surface
 * (`/admin/uploads*`, `/admin/load-sources/*`) that this console drove.
 *
 * The replacement explicit per-category source-file upload UI is tracked by
 * T-209 (`/admin/source-files`). Until then this is an intentional placeholder
 * so the route keeps building and does not call removed backend endpoints.
 */
export function LoadConsole() {
  return (
    <Panel title="Source Upload">
      <div className="form-grid">
        <p className="form-note">
          기존 자동 감지 기반 업로드 세트 화면은 제거되었습니다 (T-201). 카테고리별 명시적
          업로드 UI는 T-209(`/admin/source-files`)에서 제공됩니다.
        </p>
        <p className="form-note">
          MV refresh / 적재 작업은 Jobs 화면 또는 ktgctl CLI를 사용하세요.
        </p>
      </div>
    </Panel>
  );
}
