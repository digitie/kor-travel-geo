import type { Metadata } from "next";
import { BackupsPanel } from "@/components/admin/BackupsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.backups.title,
  description: ADMIN_PAGES.backups.description
};

export default function BackupsPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.backups.title}
        description={ADMIN_PAGES.backups.description}
      />
      <BackupsPanel />
    </>
  );
}
