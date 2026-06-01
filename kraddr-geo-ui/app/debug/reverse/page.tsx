import type { Metadata } from "next";
import { ReverseDebugger } from "@/components/debug/ReverseDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Reverse Debug",
  description: "좌표 주변의 도로명과 지번 후보를 확인하는 디버그 화면"
};

export default function ReversePage() {
  return (
    <>
      <PageHeader title="Reverse" description="좌표 주변의 도로명·지번 후보 확인" />
      <ReverseDebugger />
    </>
  );
}
