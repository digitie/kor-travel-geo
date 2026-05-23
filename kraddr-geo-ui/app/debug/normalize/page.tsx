import { NormalizeDebugger } from "@/components/debug/NormalizeDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export default function NormalizePage() {
  return (
    <>
      <PageHeader title="Normalize" description="주소 문자열의 행정구역·도로명 토큰 확인" />
      <NormalizeDebugger />
    </>
  );
}
