import type { Metadata } from "next";
import { NormalizeDebugger } from "@/components/debug/NormalizeDebugger";
import { PageHeader } from "@/components/ui/PageHeader";
import { DEBUG_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: DEBUG_PAGES.normalize.title,
  description: "주소 문자열 토큰화를 확인하는 디버그 화면"
};

export default function NormalizePage() {
  return (
    <>
      <PageHeader title={DEBUG_PAGES.normalize.title} description={DEBUG_PAGES.normalize.description} />
      <NormalizeDebugger />
    </>
  );
}
