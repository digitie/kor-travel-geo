import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default async function ConsistencyReportPage({
  params
}: {
  params: Promise<{ report_id: string }>;
}) {
  const { report_id } = await params;
  return (
    <>
      <PageHeader title="Consistency" description="C1~C10 정합성 sample 분석과 수동 판정" />
      <ConsistencyPanel initialReportId={report_id} />
    </>
  );
}
