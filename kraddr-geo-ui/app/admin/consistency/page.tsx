import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function ConsistencyPage() {
  return (
    <>
      <PageHeader title="Consistency" description="C1~C10 정합성 리포트와 swap gate 상태 확인" />
      <ConsistencyPanel />
    </>
  );
}
