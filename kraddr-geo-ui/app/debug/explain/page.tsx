import { ExplainDebugger } from "@/components/debug/ExplainDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export default function ExplainPage() {
  return (
    <>
      <PageHeader title="Explain" description="운영 엔진과 같은 search_path에서 실행 계획 확인" />
      <ExplainDebugger />
    </>
  );
}
