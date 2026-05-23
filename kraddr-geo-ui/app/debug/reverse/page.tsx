import { ReverseDebugger } from "@/components/debug/ReverseDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export default function ReversePage() {
  return (
    <>
      <PageHeader title="Reverse" description="좌표 주변의 도로명·지번 후보 확인" />
      <ReverseDebugger />
    </>
  );
}
