import type { Metadata } from "next";
import { SourceFilesPanel } from "@/components/admin/source-files/SourceFilesPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Source Files",
  description: "원천 파일 업로드·목록·매칭 세트·RustFS 정합성·현재 구성 관리"
};

export default function SourceFilesPage() {
  return (
    <>
      <PageHeader
        title="Source Files"
        description="카테고리별 업로드, 파일 목록, 매칭 세트, RustFS 정합성, 현재 구성, 검증 케이스"
      />
      <SourceFilesPanel />
    </>
  );
}
