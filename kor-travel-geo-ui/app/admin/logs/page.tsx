import { LogsPanel } from "@/components/admin/LogsPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function LogsPage() {
  return (
    <>
      <PageHeader title="Logs" description="load_jobs에 영속된 최근 진행 로그 확인" />
      <LogsPanel />
    </>
  );
}
