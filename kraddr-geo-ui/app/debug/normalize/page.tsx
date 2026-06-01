import type { Metadata } from "next";
import { NormalizeDebugger } from "@/components/debug/NormalizeDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Normalize Debug",
  description: "주소 문자열 토큰화를 확인하는 디버그 화면"
};

export default function NormalizePage() {
  return (
    <>
      <PageHeader title="Normalize" description="주소 문자열의 행정구역·도로명 토큰 확인" />
      <NormalizeDebugger />
    </>
  );
}
