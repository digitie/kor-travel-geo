import type { Metadata } from "next";

import { FilesPanel } from "@/components/admin/FilesPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.files.title,
  description: ADMIN_PAGES.files.description
};

export default function FilesPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.files.title}
        description={ADMIN_PAGES.files.description}
      />
      <FilesPanel />
    </>
  );
}
