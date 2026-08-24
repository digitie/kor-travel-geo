import type { Metadata } from "next";
import { OpsPanel } from "@/components/admin/OpsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.ops.title,
  description: ADMIN_PAGES.ops.description
};

export default function OpsPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.ops.title}
        description={ADMIN_PAGES.ops.description}
      />
      <OpsPanel />
    </>
  );
}
