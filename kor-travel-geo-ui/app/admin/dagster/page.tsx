import type { Metadata } from "next";

import { DagsterPanel } from "@/components/admin/DagsterPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.dagster.title,
  description: ADMIN_PAGES.dagster.description
};

export default function DagsterPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.dagster.title}
        description={ADMIN_PAGES.dagster.description}
      />
      <DagsterPanel />
    </>
  );
}
