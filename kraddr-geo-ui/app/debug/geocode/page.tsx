import type { Metadata } from "next";
import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { RegionsWithinRadiusDebugger } from "@/components/debug/RegionsWithinRadiusDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export const metadata: Metadata = {
  title: "Geocode Debug",
  description: "주소와 POI 반경 행정구역을 확인하는 디버그 화면"
};

export default function GeocodePage() {
  return (
    <>
      <PageHeader title="Geocode" description="주소 좌표와 POI 반경 행정구역 확인" />
      <div className="grid">
        <GeocodeDebugger />
        <RegionsWithinRadiusDebugger />
      </div>
    </>
  );
}
