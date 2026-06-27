import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type Color = "green" | "amber" | "red" | "blue" | "gray" | "indigo";

interface BadgeProps {
  color?: Color;
  children: ReactNode;
  className?: string;
}

const colorClasses: Record<Color, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-700 ring-amber-600/20",
  red: "bg-red-50 text-red-700 ring-red-600/20",
  blue: "bg-blue-50 text-blue-700 ring-blue-600/20",
  gray: "bg-surface text-ink-600 ring-ink-400/20",
  indigo: "bg-primary-50 text-primary-700 ring-primary-600/20",
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
