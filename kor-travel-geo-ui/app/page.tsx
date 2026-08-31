import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  // `absolute` so the root template does not render "Geocoder Admin UI · Geocoder Admin UI".
  // Unobservable today because this page redirects before any HTML is served — but it stops
  // being unobservable the moment the redirect goes away.
  title: { absolute: "Geocoder Admin UI" },
  description: "도로명주소 지오코딩 디버그 화면으로 이동"
};

export default function HomePage() {
  redirect("/debug/geocode");
}
