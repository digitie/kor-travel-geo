import type { Metadata } from "next";
import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.consistency.title,
  description: ADMIN_PAGES.consistency.description
};

export default function ConsistencyPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.consistency.title}
        description={ADMIN_PAGES.consistency.description}
      />
      <ConsistencyPanel />
    </>
  );
}
