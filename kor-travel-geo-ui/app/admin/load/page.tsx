import { LoadConsole } from "@/components/admin/LoadConsole";
import { PageHeader } from "@/components/ui/PageHeader";

export default function LoadPage() {
  return (
    <>
      <PageHeader title="Load" description="분기 풀로드 DAG와 MV refresh 작업 제어" />
      <LoadConsole />
    </>
  );
}
