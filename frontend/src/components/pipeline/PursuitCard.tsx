"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn, safeHttpUrl } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import { Badge } from "@/components/ui/Badge";
import { DaysBadge } from "@/components/ui/DaysBadge";
import { Spinner } from "@/components/ui/Spinner";
import {
  PURSUIT_STAGES,
  removePursuit,
  updatePursuitStage,
  type PursuitItem,
  type PursuitStage,
} from "@/lib/api/pursuits";

export function PursuitCard({ item }: { item: PursuitItem }) {
  const qc = useQueryClient();
  const o = item.opportunity;
  const idx = PURSUIT_STAGES.findIndex((s) => s.key === item.stage);
  const prev = idx > 0 ? PURSUIT_STAGES[idx - 1].key : null;
  const next = idx < PURSUIT_STAGES.length - 1 ? PURSUIT_STAGES[idx + 1].key : null;

  const move = useMutation({
    mutationFn: (stage: PursuitStage) => updatePursuitStage(o.opportunity_id, stage),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pursuits"] });
      qc.invalidateQueries({ queryKey: ["dashboard", "stats"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => removePursuit(o.opportunity_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pursuits"] }),
  });

  const busy = move.isPending || remove.isPending;
  const sourceUrl = safeHttpUrl(o.detail_url);

  return (
    <div
      aria-busy={busy}
      className={cn(
        "relative rounded-lg border border-surface-border bg-surface-card p-3 shadow-sm transition-opacity",
        busy && "pointer-events-none opacity-60"
      )}
    >
      {busy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-surface-card/50">
          <Spinner size="sm" />
        </div>
      )}
      <div className="flex items-start justify-between gap-2">
        <p className="truncate text-[11px] text-ink-400">{o.agency}</p>
        <button
          onClick={() => remove.mutate()}
          disabled={busy}
          aria-label="진행에서 제거"
          className="shrink-0 rounded p-0.5 text-ink-400 hover:bg-red-50 dark:bg-red-500/15 hover:text-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <h3 className="mt-0.5 line-clamp-2 text-sm font-semibold leading-snug text-ink">{o.title}</h3>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {o.score != null && <span className="font-semibold text-primary-600 dark:text-primary-400">적합도 {o.score}</span>}
        {o.d_day != null && <DaysBadge dDay={o.d_day} />}
        <Badge color="gray">{sourceLabel(o.source)}</Badge>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-surface-border pt-2">
        <div className="flex items-center gap-1">
          <button
            onClick={() => prev && move.mutate(prev)}
            disabled={!prev || busy}
            aria-label="이전 단계로"
            className="flex h-6 w-6 items-center justify-center rounded-md border border-surface-border text-ink-600 hover:bg-surface disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
          </button>
          <button
            onClick={() => next && move.mutate(next)}
            disabled={!next || busy}
            aria-label="다음 단계로"
            className="flex h-6 w-6 items-center justify-center rounded-md border border-surface-border text-ink-600 hover:bg-surface disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded px-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            원문 →
          </a>
        ) : (
          <span className="text-xs text-ink-400">원문 없음</span>
        )}
      </div>
    </div>
  );
}
