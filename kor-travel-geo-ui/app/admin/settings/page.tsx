import { SettingsPanel } from "@/components/admin/SettingsPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.settings.title}
        description={ADMIN_PAGES.settings.description}
      />
      <SettingsPanel />
    </>
  );
}
