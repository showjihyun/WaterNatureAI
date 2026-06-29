import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type Color = "green" | "amber" | "red" | "blue" | "gray" | "indigo";

interface BadgeProps {
  color?: Color;
  children: ReactNode;
  className?: string;
}

const colorClasses: Record<Color, string> = {
  green: "bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-600/20",
  amber: "bg-amber-50 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 ring-amber-600/20",
  red: "bg-red-50 dark:bg-red-500/15 text-red-700 dark:text-red-300 ring-red-600/20",
  blue: "bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 ring-blue-600/20",
  gray: "bg-surface text-ink-600 ring-ink-400/20",
  indigo: "bg-primary-50 dark:bg-primary-500/15 text-primary-700 dark:text-primary-300 ring-primary-600/20",
};

export function Badge({ color = "gray", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset",
        colorClasses[color],
        className
      )}
    >
      {children}
    </span>
  );
}
