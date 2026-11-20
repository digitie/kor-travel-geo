import type { Metadata } from "next";
import { ReverseDebugger } from "@/components/debug/ReverseDebugger";
import { PageHeader } from "@/components/ui/PageHeader";
import { DEBUG_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: DEBUG_PAGES.reverse.title,
  description: "좌표 주변의 도로명과 지번 후보를 확인하는 디버그 화면"
};

export default function ReversePage() {
  return (
    <>
      <PageHeader title={DEBUG_PAGES.reverse.title} description={DEBUG_PAGES.reverse.description} />
      <ReverseDebugger />
    </>
  );
}
