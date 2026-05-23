import { TableStatsPanel } from "@/components/admin/TableStatsPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function TablesPage() {
  return (
    <>
      <PageHeader title="Tables" description="PostgreSQL 테이블 행 수와 디스크 사용량 확인" />
      <TableStatsPanel />
    </>
  );
}
