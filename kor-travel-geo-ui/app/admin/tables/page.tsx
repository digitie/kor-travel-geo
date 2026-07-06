import { TableStatsPanel } from "@/components/admin/TableStatsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export default function TablesPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.tables.title}
        description={ADMIN_PAGES.tables.description}
      />
      <TableStatsPanel />
    </>
  );
}
