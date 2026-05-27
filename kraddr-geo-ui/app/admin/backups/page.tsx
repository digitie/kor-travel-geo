import { BackupsPanel } from "@/components/admin/BackupsPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function BackupsPage() {
  return (
    <>
      <PageHeader title="DB Backups" description="백업, 복원, artifact 다운로드" />
      <BackupsPanel />
    </>
  );
}
