import { SettingsPanel } from "@/components/admin/SettingsPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="지도와 운영 콘솔 런타임 설정" />
      <SettingsPanel />
    </>
  );
}
