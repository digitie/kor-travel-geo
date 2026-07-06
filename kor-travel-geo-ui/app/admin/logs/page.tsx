import { LogsPanel } from "@/components/admin/LogsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

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
