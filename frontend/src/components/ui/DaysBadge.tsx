import { cn, formatDDay, getDDayUrgency } from "@/lib/utils";

const dDayStyles: Record<ReturnType<typeof getDDayUrgency>, string> = {
  critical: "bg-red-600 text-white shadow-sm",
  warning: "bg-amber-500 text-white",
  normal: "bg-surface text-ink-600 ring-1 ring-inset ring-surface-border",
};

/**
 * 마감 D-day 배지 — Row/PursuitCard에 중복되던 dDayStyles 맵을 통일.
 * whitespace-nowrap로 "마감일 미정"이 좁은 칸에서 "미/정"으로 쪼개지는 줄바꿈을 방지.
 */
export function DaysBadge({
  dDay,
  className,
}: {
  dDay: number | null | undefined;
  className?: string;
}) {
  const urgency = getDDayUrgency(dDay);
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-lg px-2.5 py-1 font-display text-xs font-bold tabular-nums",
        dDayStyles[urgency],
        className
      )}
    >
      {formatDDay(dDay)}
    </span>
  );
}
