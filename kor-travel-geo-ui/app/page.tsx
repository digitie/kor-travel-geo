import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  // `absolute` so the root template does not render "kor-travel-geo-ui · kor-travel-geo-ui".
  // Unobservable today because this page redirects before any HTML is served — but it stops
  // being unobservable the moment the redirect goes away.
  title: { absolute: "kor-travel-geo-ui" },
  description: "도로명주소 지오코딩 디버그 화면으로 이동"
};

export default function HomePage() {
  redirect("/debug/geocode");
}
