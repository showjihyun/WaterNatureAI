"use client";

import type { ReactNode } from "react";
import { Sidebar, MobileNav } from "./Sidebar";
import { NotificationBell } from "./NotificationBell";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { AuthGuard } from "@/components/auth/AuthGuard";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-surface">
        {/* 키보드 사용자: 사이드바 건너뛰고 본문으로 */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-slate-900 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
        >
          본문 바로가기
        </a>
        <Sidebar />
        {/* min-w-0: 자식 콘텐츠가 flex 트랙을 넘쳐 가로 스크롤 만드는 것 방지 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <MobileNav />
          {/* 데스크톱 상단 유틸리티 바 — 알림 벨 */}
          <div className="hidden h-14 shrink-0 items-center justify-end gap-1 border-b border-surface-border bg-surface-card px-6 lg:flex">
            <ThemeToggle />
            <NotificationBell />
          </div>
          <main id="main-content" className="flex-1 overflow-y-auto">
            {/* 화면 전체 폭 사용(반응형) — 사이드바를 제외한 본문 영역을 가득 채움 */}
            <div className="min-h-full p-4 sm:p-6">{children}</div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
