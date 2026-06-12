import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "kor-travel-geo-ui",
  description: "도로명주소 지오코딩 디버그 화면으로 이동"
};

export default function HomePage() {
  redirect("/debug/geocode");
}
