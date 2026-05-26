import { OpsPanel } from "@/components/admin/OpsPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function OpsPage() {
  return (
    <>
      <PageHeader title="Ops" description="운영 감사, 데이터셋 스냅샷, 릴리스와 artifact 상태 확인" />
      <OpsPanel />
    </>
  );
}
