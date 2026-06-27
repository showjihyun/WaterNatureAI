"use client";

import { useEffect, useRef, useState } from "react";

const REASONS: { key: string; label: string }[] = [
  { key: "category", label: "분야가 안 맞아요" },
  { key: "budget", label: "사업 규모가 안 맞아요" },
  { key: "agency", label: "이 기관은 관심 없어요" },
  { key: "other", label: "기타" },
];

/** '관심없음' 버튼 + 사유 선택 팝오버. 사유 선택 시 onHide(reason) 호출. */
export function HideMenu({ onHide }: { onHide: (reason: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="관심없음"
        aria-haspopup="menu"
        aria-expanded={open}
        title="관심없음 (추천에서 숨기기)"
        className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-ink-400 transition-colors hover:bg-gray-200 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.243 4.243L9.88 9.88" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-8 z-50 w-44 overflow-hidden rounded-xl border border-surface-border bg-surface-card shadow-lg"
        >
          <p className="border-b border-surface-border px-3 py-2 text-xs font-semibold text-ink-600">
            왜 관심없으세요?
          </p>
          {REASONS.map((r) => (
            <button
              key={r.key}
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onHide(r.key);
              }}
              className="block w-full px-3 py-2 text-left text-xs text-ink-600 transition-colors hover:bg-surface focus-visible:bg-surface focus-visible:outline-none"
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
