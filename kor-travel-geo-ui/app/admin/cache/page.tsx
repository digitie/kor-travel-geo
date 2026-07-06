import { CachePanel } from "@/components/admin/CachePanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export default function CachePage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.cache.title}
        description={ADMIN_PAGES.cache.description}
      />
      <CachePanel />
    </>
  );
}
