import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Clean Chat 모듈 시뮬레이터",
  description: "입력을 넣으면 실제 모듈 함수(로컬 서버)를 실행해 output 을 보여 주는 개발 도구",
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
