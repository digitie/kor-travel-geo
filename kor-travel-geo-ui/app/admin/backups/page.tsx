import { BackupsPanel } from "@/components/admin/BackupsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

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
