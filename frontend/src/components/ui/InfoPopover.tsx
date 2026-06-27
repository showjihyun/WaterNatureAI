"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface InfoPopoverProps {
  title: string;
  children: ReactNode;
  ariaLabel?: string;
  className?: string;
}

export function InfoPopover({ title, children, ariaLabel, className }: InfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside mousedown and Esc key
  useEffect(() => {
    if (!open) return;

    function handleMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className={cn("relative inline-flex items-center", className)}>
      {/* Trigger button */}
      <button
        type="button"
        aria-label={ariaLabel ?? `${title} 도움말`}
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-gray-200 text-gray-500 hover:bg-gray-300 hover:text-gray-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-gray-400 shrink-0"
      >
        <span className="text-[10px] font-bold leading-none select-none">?</span>
      </button>

      {/* Popover panel */}
      {open && (
        <div
          role="dialog"
          aria-label={title}
          className="absolute left-0 top-6 z-50 w-72 max-w-[calc(100vw-2rem)] rounded-xl border border-surface-border bg-surface-card shadow-lg"
        >
          {/* Header */}
          <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-2.5">
            <span className="text-sm font-semibold text-gray-800">{title}</span>
            <button
              type="button"
              aria-label="닫기"
              onClick={() => setOpen(false)}
              className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400"
            >
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Body */}
          <div className="px-4 py-3 text-xs text-gray-600 leading-relaxed">{children}</div>
        </div>
      )}
    </div>
  );
}
