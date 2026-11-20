import type { Metadata } from "next";
import { ExplainDebugger } from "@/components/debug/ExplainDebugger";
import { PageHeader } from "@/components/ui/PageHeader";
import { DEBUG_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: DEBUG_PAGES.explain.title,
  description: "운영 search_path 기준 SQL 실행 계획을 확인하는 디버그 화면"
};

export default function ExplainPage() {
  return (
    <>
      <PageHeader title={DEBUG_PAGES.explain.title} description={DEBUG_PAGES.explain.description} />
      <ExplainDebugger />
    </>
  );
}
