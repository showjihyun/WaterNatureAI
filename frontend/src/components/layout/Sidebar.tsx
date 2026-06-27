"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { clearTokens } from "@/lib/api/client";
import { Brand } from "@/components/ui/Brand";
import { NotificationBell } from "./NotificationBell";

interface NavLeaf {
  href: string;
  label: string;
  icon: React.ReactNode;
}
interface NavGroup {
  label: string;
  icon: React.ReactNode;
  children: NavLeaf[];
}
type NavEntry = NavLeaf | NavGroup;

const dashboardIcon = (
  <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </svg>
);

const navEntries: NavEntry[] = [
  { href: "/dashboard", label: "대시보드", icon: dashboardIcon },
  {
    href: "/opportunities",
    label: "공고 탐색",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.3-4.3" />
      </svg>
    ),
  },
  {
    label: "내 공고",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
      </svg>
    ),
    children: [
      {
        href: "/saved",
        label: "관심 공고",
        icon: (
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
          </svg>
        ),
      },
      {
        href: "/pipeline",
        label: "진행 관리",
        icon: (
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="5" height="16" rx="1.5" />
            <rect x="9.5" y="4" width="5" height="10" rx="1.5" />
            <rect x="16" y="4" width="5" height="13" rx="1.5" />
          </svg>
        ),
      },
    ],
  },
  {
    href: "/settings",
    label: "설정",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

const leafClasses = (active: boolean) =>
  cn(
    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400",
    active
      ? "bg-primary-500/15 text-primary-300 border-l-2 border-primary-400"
      : "text-slate-300/70 hover:bg-white/5 hover:text-white"
  );

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavLeaf;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link href={item.href} onClick={onNavigate} className={leafClasses(active)}>
      <span className={cn("shrink-0", active ? "text-primary-400" : "text-slate-400")}>
        {item.icon}
      </span>
      {item.label}
    </Link>
  );
}

/** "내 공고" 그룹 — 자식(관심/진행) 확장. 자식 경로에 있으면 기본 펼침. */
function NavGroupItem({
  group,
  pathname,
  onNavigate,
}: {
  group: NavGroup;
  pathname: string | null;
  onNavigate?: () => void;
}) {
  const childActive = group.children.some((c) => pathname?.startsWith(c.href));
  const [open, setOpen] = useState(childActive);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400",
          childActive ? "text-primary-300" : "text-slate-300/70 hover:bg-white/5 hover:text-white"
        )}
      >
        <span className={cn("shrink-0", childActive ? "text-primary-400" : "text-slate-400")}>
          {group.icon}
        </span>
        {group.label}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={cn("ml-auto h-4 w-4 transition-transform", open && "rotate-180")}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="mt-0.5 space-y-0.5 border-l border-white/10 pl-3">
          {group.children.map((c) => (
            <NavLink
              key={c.href}
              item={c}
              active={!!pathname?.startsWith(c.href)}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** 워드마크(레이더 마크 + WaterNatureAI). 드로어에서는 onClose로 닫기 버튼 노출. */
function Wordmark({ onClose }: { onClose?: () => void }) {
  return (
    <div className="flex h-14 items-center gap-2 px-4 border-b border-white/10">
      <Brand tone="dark" textClassName="text-sm" />
      <span className="flex-1" />
      {onClose && (
        <button
          onClick={onClose}
          aria-label="메뉴 닫기"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

/** 네비 + 로그아웃. onNavigate는 모바일 드로어에서 항목 클릭 시 닫기 용도. */
function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    onNavigate?.();
    clearTokens();
    router.push("/login");
  }

  return (
    <>
      <Wordmark onClose={onNavigate} />
      <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
        {navEntries.map((entry) =>
          "children" in entry ? (
            <NavGroupItem
              key={entry.label}
              group={entry}
              pathname={pathname}
              onNavigate={onNavigate}
            />
          ) : (
            <NavLink
              key={entry.href}
              item={entry}
              active={!!pathname?.startsWith(entry.href)}
              onNavigate={onNavigate}
            />
          )
        )}
      </nav>
      <div className="border-t border-white/10 p-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-white/5 hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
          </svg>
          로그아웃
        </button>
      </div>
    </>
  );
}

/** 데스크톱(lg+) 고정 사이드바. */
export function Sidebar() {
  return (
    <aside className="hidden lg:flex h-screen w-56 flex-col bg-ink">
      <SidebarContent />
    </aside>
  );
}

/** 모바일(lg 미만) 상단 앱바 + 햄버거 드로어. */
export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <header className="lg:hidden flex h-14 shrink-0 items-center gap-3 border-b border-surface-border bg-surface-card px-4">
        <button
          onClick={() => setOpen(true)}
          aria-label="메뉴 열기"
          className="flex h-9 w-9 items-center justify-center rounded-lg text-ink-600 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <Brand tone="light" textClassName="text-sm" />
        <div className="ml-auto">
          <NotificationBell />
        </div>
      </header>

      {open && (
        <div className="lg:hidden fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="메뉴">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-ink shadow-xl">
            <SidebarContent onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
