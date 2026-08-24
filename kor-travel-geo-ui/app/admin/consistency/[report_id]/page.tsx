import type { Metadata } from "next";
import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: "정합성 리포트"
};

export default async function ConsistencyReportPage({
  params
}: {
  params: Promise<{ report_id: string }>;
}) {
  const { report_id } = await params;
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.consistency.title}
        description={ADMIN_PAGES.consistency.description}
      />
      <ConsistencyPanel initialReportId={report_id} />
    </>
  );
}
