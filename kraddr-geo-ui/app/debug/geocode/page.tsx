import type { Metadata } from "next";
import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Geocode Debug",
  description: "주소를 좌표와 geometry 후보로 확인하는 디버그 화면"
};

export default function GeocodePage() {
  return (
    <>
      <PageHeader title="Geocode" description="주소를 좌표와 우편번호 확장 정보로 확인" />
      <GeocodeDebugger />
    </>
  );
}
