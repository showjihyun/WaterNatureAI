import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/providers/QueryProvider";

export const metadata: Metadata = {
  title: "WaterNature AI — 공공사업 추천",
  description: "AI가 분석한 맞춤 공공 사업 기회를 매일 추천받으세요.",
};

// paint 전에 테마 적용(무플래시 FOUC 방지). localStorage('theme') 우선, 없으면 OS 설정.
const themeScript = `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark');}}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
