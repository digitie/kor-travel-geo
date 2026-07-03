import { ConsistencyPanel } from "@/components/admin/ConsistencyPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

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
