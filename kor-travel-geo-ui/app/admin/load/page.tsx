import { LoadConsole } from "@/components/admin/LoadConsole";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export default function LoadPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.load.title}
        description={ADMIN_PAGES.load.description}
      />
      <LoadConsole />
    </>
  );
}
