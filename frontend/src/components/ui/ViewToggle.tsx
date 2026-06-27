"use client";

import type { ViewMode } from "@/lib/useViewMode";
import { cn } from "@/lib/utils";

interface ViewToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
}

const buttonBase =
  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500";

/**
 * Small segmented control for switching between the card grid and the list
 * (table readout). Meant to sit at the top-right of a list section.
 */
export function ViewToggle({ mode, onChange, className }: ViewToggleProps) {
  return (
    <div
      role="group"
      aria-label="보기 방식"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border border-surface-border bg-surface p-0.5",
        className
      )}
    >
      <button
        type="button"
        aria-pressed={mode === "card"}
        aria-label="카드 보기"
        onClick={() => onChange("card")}
        className={cn(
          buttonBase,
          mode === "card"
            ? "bg-primary-50 text-primary-700 shadow-sm"
            : "text-ink-400 hover:text-ink-600"
        )}
      >
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <rect x="4" y="4" width="7" height="7" rx="1.5" />
          <rect x="13" y="4" width="7" height="7" rx="1.5" />
          <rect x="4" y="13" width="7" height="7" rx="1.5" />
          <rect x="13" y="13" width="7" height="7" rx="1.5" />
        </svg>
        카드
      </button>
      <button
        type="button"
        aria-pressed={mode === "list"}
        aria-label="리스트 보기"
        onClick={() => onChange("list")}
        className={cn(
          buttonBase,
          mode === "list"
            ? "bg-primary-50 text-primary-700 shadow-sm"
            : "text-ink-400 hover:text-ink-600"
        )}
      >
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
        리스트
      </button>
    </div>
  );
}
