"use client";

import { useState } from "react";
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

const TABS: { id: SourceFilesTabId; label: string }[] = [
  { id: "upload", label: "업로드" },
  { id: "list", label: "목록" },
  { id: "match", label: "매칭 세트" },
  { id: "reconcile", label: "RustFS 정합성" },
  { id: "current", label: "현재 구성" },
  { id: "cases", label: "검증 케이스" }
];

export function SourceFilesPanel({
  initialTab = "upload"
}: {
  initialTab?: SourceFilesTabId;
}) {
  const [activeTab, setActiveTab] = useState<SourceFilesTabId>(initialTab);

  return (
    <div className="source-files-shell">
      <nav aria-label="원천 파일 탭" className="case-tabs">
        <div
          aria-label="원천 파일 관리 탭"
          aria-orientation="horizontal"
          className="case-tab-list"
          role="tablist"
        >
          {TABS.map((tab) => {
            const isSelected = tab.id === activeTab;
            return (
              <button
                aria-controls="source-files-panel"
                aria-selected={isSelected}
                className={isSelected ? "case-tab active" : "case-tab"}
                id={`source-tab-${tab.id}`}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                role="tab"
                type="button"
              >
                <strong>{tab.label}</strong>
              </button>
            );
          })}
        </div>
      </nav>

      <section
        aria-labelledby={`source-tab-${activeTab}`}
        className="source-files-pane"
        id="source-files-panel"
        role="tabpanel"
      >
        {activeTab === "upload" ? <UploadTab /> : null}
        {activeTab === "list" ? <ListTab /> : null}
        {activeTab === "match" ? <MatchSetsTab /> : null}
        {activeTab === "reconcile" ? <ReconcileTab /> : null}
        {activeTab === "current" ? <CurrentConfigTab /> : null}
        {activeTab === "cases" ? <SourceCasesTab /> : null}
      </section>
    </div>
  );
}
