import { formatScore } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null | undefined;
  showBar?: boolean;
  className?: string;
}

export function ScoreBadge({ score, showBar = true, className }: ScoreBadgeProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex flex-col items-start">
        <span className="font-display tabular-nums text-base font-bold text-ink leading-none">
          {formatScore(score)}
        </span>
        <span className="text-[10px] font-medium text-ink-400 uppercase tracking-wide mt-0.5">
          적합도
        </span>
      </div>
      {showBar && score != null && (
        <div className="h-1.5 w-20 rounded-full bg-surface-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary-500 transition-all"
            style={{ width: `${Math.min(score, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
