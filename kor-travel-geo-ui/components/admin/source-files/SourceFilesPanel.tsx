"use client";

import { useState } from "react";
import { AdminTabs, AdminTabsContent } from "@/components/admin/shared/AdminTabs";
import { CurrentConfigTab } from "@/components/admin/source-files/CurrentConfigTab";
import { ListTab } from "@/components/admin/source-files/ListTab";
import { MatchSetsTab } from "@/components/admin/source-files/MatchSetsTab";
import { ReconcileTab } from "@/components/admin/source-files/ReconcileTab";
import { SourceCasesTab } from "@/components/admin/source-files/SourceCasesTab";
import { UploadTab } from "@/components/admin/source-files/UploadTab";

export type SourceFilesTabId =
  | "upload"
  | "list"
  | "match"
  | "reconcile"
  | "current"
  | "cases";

const TABS: { value: SourceFilesTabId; label: string }[] = [
  { value: "upload", label: "업로드" },
  { value: "list", label: "목록" },
  { value: "match", label: "매칭 세트" },
  { value: "reconcile", label: "RustFS 정합성" },
  { value: "current", label: "현재 구성" },
  { value: "cases", label: "검증 케이스" }
];

export function SourceFilesPanel({
  initialTab = "upload"
}: {
  initialTab?: SourceFilesTabId;
}) {
  const [activeTab, setActiveTab] = useState<SourceFilesTabId>(initialTab);

  return (
    <div className="source-files-shell">
      <AdminTabs
        label="원천 파일 관리 탭"
        value={activeTab}
        onValueChange={setActiveTab}
        items={TABS}
      >
        <AdminTabsContent className="source-files-pane" value="upload">
          <UploadTab />
        </AdminTabsContent>
        <AdminTabsContent className="source-files-pane" value="list">
          <ListTab />
        </AdminTabsContent>
        <AdminTabsContent className="source-files-pane" value="match">
          <MatchSetsTab />
        </AdminTabsContent>
        <AdminTabsContent className="source-files-pane" value="reconcile">
          <ReconcileTab />
        </AdminTabsContent>
        <AdminTabsContent className="source-files-pane" value="current">
          <CurrentConfigTab />
        </AdminTabsContent>
        <AdminTabsContent className="source-files-pane" value="cases">
          <SourceCasesTab />
        </AdminTabsContent>
      </AdminTabs>
    </div>
  );
}
