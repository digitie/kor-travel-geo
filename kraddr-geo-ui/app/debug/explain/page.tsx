import type { Metadata } from "next";
import { ExplainDebugger } from "@/components/debug/ExplainDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Explain Debug",
  description: "운영 search_path 기준 SQL 실행 계획을 확인하는 디버그 화면"
};

export default function ExplainPage() {
  return (
    <>
      <PageHeader title="Explain" description="운영 엔진과 같은 search_path에서 실행 계획 확인" />
      <ExplainDebugger />
    </>
  );
}
