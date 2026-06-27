import { formatDDay, getDDayUrgency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface DaysBadgeProps {
  dDay: number | null | undefined;
  deadline?: string | null;
  className?: string;
}

export function DaysBadge({ dDay, deadline, className }: DaysBadgeProps) {
  const urgency = getDDayUrgency(dDay);
  const label = formatDDay(dDay);

  const styles = {
    critical: "bg-red-600 text-white shadow-sm",
    warning: "bg-amber-500 text-white",
    normal: "bg-slate-100 text-slate-600",
  };

  return (
    <div className={cn("flex flex-col items-end gap-0.5", className)}>
      <span
        className={cn(
          "inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold tabular-nums font-display",
          styles[urgency]
        )}
      >
        {label}
      </span>
      {deadline && (
        <span className="text-xs text-gray-400">
          {new Date(deadline).toLocaleDateString("ko-KR", {
            month: "numeric",
            day: "numeric",
          })}
          마감
        </span>
      )}
    </div>
  );
}
