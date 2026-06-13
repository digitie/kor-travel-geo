import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import { WebVitalsReporter } from "@/components/metrics/WebVitalsReporter";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "kor-travel-geo-ui",
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
