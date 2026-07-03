import { OpsPanel } from "@/components/admin/OpsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

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
