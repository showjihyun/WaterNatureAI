"use client";

import type { SortKey } from "@/types/api";
import { cn } from "@/lib/utils";

export type { SortKey };

interface SortControlProps {
  value: SortKey;
  onChange: (value: SortKey) => void;
  className?: string;
}

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "score", label: "적합도순" },
  { value: "deadline", label: "마감 임박순" },
  { value: "posted", label: "최신 등록순" },
  { value: "budget", label: "예산 높은순" },
  { value: "feasibility", label: "수행 가능성순" },
];

/**
 * Compact sort selector meant to sit beside the ViewToggle at the top of a
 * list/grid section. Native <select> for determinism + built-in accessibility;
 * styled with the console's cyan focus ring and ink text.
 */
export function SortControl({ value, onChange, className }: SortControlProps) {
  return (
    <div className={cn("inline-flex items-center gap-1.5", className)}>
      <label htmlFor="sort-control" className="sr-only">
        정렬 기준
      </label>
      <div className="relative">
        <select
          id="sort-control"
          value={value}
          onChange={(e) => onChange(e.target.value as SortKey)}
          aria-label="정렬 기준"
          className="appearance-none rounded-lg border border-surface-border bg-surface py-1 pl-2.5 pr-7 text-xs font-medium text-ink-600 transition-colors hover:text-ink focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}
