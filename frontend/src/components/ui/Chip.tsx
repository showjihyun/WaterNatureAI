import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface ChipProps {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  title?: string;
}

/**
 * 토글 칩 — 단일/다중 선택 공용 프리미티브(공고 필터 + 역량 선택).
 * aria-pressed 로 상태 전달(색 의존 제거). active=solid primary,
 * inactive=중립 보더 + primary hover. 크기는 className(px/py/text)로 조절.
 */
export function Chip({ active, onClick, children, className, title }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500",
        active
          ? "bg-primary-600 text-white shadow-sm"
          : "bg-surface border border-surface-border text-ink-600 hover:bg-primary-50 dark:hover:bg-primary-500/15 hover:text-primary-700 dark:hover:text-primary-300 hover:border-primary-300",
        className
      )}
    >
      {children}
    </button>
  );
}
