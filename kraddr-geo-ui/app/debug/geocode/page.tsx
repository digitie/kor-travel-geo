import { GeocodeDebugger } from "@/components/debug/GeocodeDebugger";
import { PageHeader } from "@/components/ui/PageHeader";

export default function GeocodePage() {
  return (
    <>
      <PageHeader title="Geocode" description="주소를 좌표와 우편번호 확장 정보로 확인" />
      <GeocodeDebugger />
    </>
  );
}
