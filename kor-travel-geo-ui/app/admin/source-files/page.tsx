import type { Metadata } from "next";
import { SourceFilesPanel } from "@/components/admin/source-files/SourceFilesPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.sourceFiles.title,
  description: ADMIN_PAGES.sourceFiles.description
};

export default function SourceFilesPage() {
  return (
    <>
      {/* 탭 라벨과 중복되던 긴 나열식 설명은 제거했다. */}
      <PageHeader
        title={ADMIN_PAGES.sourceFiles.title}
        description={ADMIN_PAGES.sourceFiles.description}
      />
      <SourceFilesPanel />
    </>
  );
}
