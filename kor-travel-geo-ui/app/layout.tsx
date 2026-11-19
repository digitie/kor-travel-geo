import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import { WebVitalsReporter } from "@/components/metrics/WebVitalsReporter";
import { Providers } from "./providers";

export const metadata: Metadata = {
  // 탭 제목은 상단 바 h1과 같은 "지오 - 페이지" 형식(@kor-travel/ui formatAdminTitle)이다.
  // `template`이 없으면 `/admin/backups`가 맨 "백업/복원"만 보였다(issue #515).
  title: {
    default: "지오",
    template: "지오 - %s"
  },
  description: "도로명주소 지오코딩 운영 도구"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <WebVitalsReporter />
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
