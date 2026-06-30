"use client";

import { useEffect, useState } from "react";

/**
 * 라이트/다크 토글. html.dark 클래스를 켜고 localStorage('theme')에 저장.
 * 초기 테마는 layout의 무플래시 인라인 스크립트가 paint 전에 적용하므로,
 * 여기선 마운트 시 현재 클래스를 읽어 아이콘만 동기화한다.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const el = document.documentElement;
    const next = !el.classList.contains("dark");
    el.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* private mode 등 — 무시 */
    }
    setDark(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "라이트 모드로 전환" : "다크 모드로 전환"}
      title={dark ? "라이트 모드" : "다크 모드"}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-600 transition-colors hover:bg-surface-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 ${className}`}
    >
      {dark ? (
        // 해(라이트로) 아이콘
        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path strokeLinecap="round" d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32 1.41-1.41" />
        </svg>
      ) : (
        // 달(다크로) 아이콘
        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
