import { CachePanel } from "@/components/admin/CachePanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function CachePage() {
  return (
    <>
      <PageHeader title="Cache" description="외부 API 캐시의 현재 크기와 hit 누적치 확인" />
      <CachePanel />
    </>
  );
}
