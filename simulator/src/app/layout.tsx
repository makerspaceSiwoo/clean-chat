import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Clean Chat 모듈 시뮬레이터",
  description: "모듈별 E2E 동작을 Mock 데이터로 확인하는 사내 테스트 도구",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>
          <AppHeader />
          <main className="mx-auto w-[1280px] px-8 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
