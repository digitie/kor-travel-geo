import type { Metadata } from "next";
import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { RegionsWithinRadiusDebugger } from "@/components/debug/RegionsWithinRadiusDebugger";
import { PageHeader } from "@/components/ui/PageHeader";
import { DEBUG_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: DEBUG_PAGES.geocode.title,
  description: "주소와 POI 반경 행정구역을 확인하는 디버그 화면"
};

export default function GeocodePage() {
  return (
    <>
      <PageHeader title={DEBUG_PAGES.geocode.title} description={DEBUG_PAGES.geocode.description} />
      <div className="grid">
        <GeocodeDebugger />
        <RegionsWithinRadiusDebugger />
      </div>
    </>
  );
}
