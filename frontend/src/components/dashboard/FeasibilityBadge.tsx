import type { FeasibilityVerdict } from "@/types/api";
import { cn } from "@/lib/utils";

interface FeasibilityBadgeProps {
  feasibility: FeasibilityVerdict | null | undefined;
  /** compact=true: show only 1 reason + overflow count (for cards).
   *  compact=false (default): show full reason list. */
  compact?: boolean;
}

const verdictStyles: Record<
  FeasibilityVerdict["verdict"],
  { badge: string; dot: string; icon: React.ReactNode }
> = {
  go: {
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    dot: "bg-emerald-500",
    icon: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
      </svg>
    ),
  },
  review: {
    badge: "bg-amber-50 text-amber-700 ring-amber-600/20",
    dot: "bg-amber-400",
    icon: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
    ),
  },
  no_go: {
    badge: "bg-red-50 text-red-700 ring-red-600/20",
    dot: "bg-red-500",
    icon: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
  },
};

export function FeasibilityBadge({ feasibility, compact = true }: FeasibilityBadgeProps) {
  if (!feasibility) return null;

  const { verdict, label, reasons } = feasibility;
  const style = verdictStyles[verdict];

  const shownReasons = compact ? reasons.slice(0, 1) : reasons;
  const hiddenCount = compact ? reasons.length - shownReasons.length : 0;

  return (
    <div className="flex flex-col gap-1">
      {/* Badge pill */}
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
          style.badge
        )}
      >
        {style.icon}
        {label}
      </span>

      {/* Reasons */}
      {shownReasons.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {shownReasons.map((reason, i) => (
            <span key={i} className="text-xs text-gray-500 leading-snug">
              {reason}
            </span>
          ))}
          {hiddenCount > 0 && (
            <span className="text-xs text-gray-400">외 {hiddenCount}건</span>
          )}
        </div>
      )}
    </div>
  );
}
