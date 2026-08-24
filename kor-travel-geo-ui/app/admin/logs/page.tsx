import type { Metadata } from "next";
import { LogsPanel } from "@/components/admin/LogsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.logs.title,
  description: ADMIN_PAGES.logs.description
};

export default function LogsPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.logs.title}
        description={ADMIN_PAGES.logs.description}
      />
      <LogsPanel />
    </>
  );
}
