"use client";

import { useQuery } from "@tanstack/react-query";
import { getReminders } from "@/lib/api/reminders";
import { formatDDay, getDDayUrgency, cn, safeHttpUrl } from "@/lib/utils";

const VIA_LABEL: Record<string, string> = { saved: "관심", pursuit: "진행" };

const dDayStyles: Record<ReturnType<typeof getDDayUrgency>, string> = {
  critical: "bg-red-600 text-white",
  warning: "bg-amber-500 text-white",
  normal: "bg-slate-100 text-slate-600",
};

/**
 * 대시보드 상단 '마감 임박' — 관심(♥)·진행 관리 공고 중 마감이 가까운 것(기본 D-3 이내).
 * 일일 추천(새 공고)과 분리된, 이미 추적 중인 공고의 마감 리마인더. 없으면 렌더 안 함.
 */
export function DeadlineReminders() {
  const { data } = useQuery({
    queryKey: ["reminders"],
    queryFn: getReminders,
    staleTime: 60 * 1000,
  });

  if (!data || data.length === 0) return null;

  return (
    <div className="mb-6 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-500/15 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300">
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3 2" />
          </svg>
        </span>
        <h2 className="text-sm font-bold text-amber-900">마감 임박</h2>
        <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-amber-200 dark:bg-amber-500/25 px-1.5 text-xs font-bold text-amber-800 dark:text-amber-300">
          {data.length}
        </span>
        <span className="ml-1 text-xs text-amber-700 dark:text-amber-300/80">관심·진행 공고의 마감이 가까워요</span>
      </div>
      <ul className="space-y-1.5">
        {data.map((it) => {
          const o = it.opportunity;
          const urgency = getDDayUrgency(o.d_day);
          const sourceUrl = safeHttpUrl(o.detail_url);
          return (
            <li
              key={o.opportunity_id}
              className="flex items-center gap-3 rounded-lg bg-surface-card/70 px-3 py-2"
            >
              <span
                className={cn(
                  "inline-flex shrink-0 items-center rounded-md px-2 py-0.5 font-display text-xs font-bold tabular-nums",
                  dDayStyles[urgency]
                )}
              >
                {formatDDay(o.d_day)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{o.title}</p>
                {o.agency && <p className="truncate text-xs text-ink-400">{o.agency}</p>}
              </div>
              <span className="hidden shrink-0 rounded-full bg-amber-100 dark:bg-amber-500/20 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300 sm:inline">
                {VIA_LABEL[it.tracked_via] ?? it.tracked_via}
              </span>
              {sourceUrl && (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-amber-800 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                >
                  원문
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
