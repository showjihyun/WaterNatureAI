"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAlerts } from "@/lib/api/alerts";
import { formatDDay, getDDayUrgency, cn, safeHttpUrl } from "@/lib/utils";
import type { RecommendationItem } from "@/types/api";

const SEEN_KEY = "wn_alerts_seen_ids";

function loadSeen(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"));
  } catch {
    return new Set();
  }
}
function saveSeen(ids: Set<string>) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(Array.from(ids).slice(-300)));
  } catch {
    // ignore
  }
}

const dDayStyles: Record<ReturnType<typeof getDDayUrgency>, string> = {
  critical: "bg-red-600 text-white",
  warning: "bg-amber-500 text-white",
  normal: "bg-slate-100 text-slate-600",
};

/** 알림 한 줄 — 마감(dday 뱃지) 또는 키워드(돋보기 칩) + 제목 + 원문. */
function AlertRow({
  item,
  variant,
  onClose,
}: {
  item: RecommendationItem;
  variant: "deadline" | "keyword";
  onClose: () => void;
}) {
  // detail_url은 외부(스크랩/LLM) 데이터 → 안전한 http(s)만 외부링크, 아니면 내부 워치로.
  const sourceUrl = safeHttpUrl(item.detail_url);
  // 원문 URL 없을 때 내부 폴백: 마감(관심/진행)→대시보드 리마인더, 키워드→워치 탭.
  const fallbackUrl = variant === "deadline" ? "/dashboard" : "/opportunities?tab=watch";
  return (
    <a
      href={sourceUrl || fallbackUrl}
      target={sourceUrl ? "_blank" : undefined}
      rel="noreferrer"
      onClick={onClose}
      className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-surface"
    >
      {variant === "deadline" ? (
        <span
          className={cn(
            "mt-0.5 inline-flex shrink-0 items-center rounded px-1.5 py-0.5 font-display text-[11px] font-bold tabular-nums",
            dDayStyles[getDDayUrgency(item.d_day)]
          )}
        >
          {formatDDay(item.d_day)}
        </span>
      ) : (
        <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary-50 dark:bg-primary-500/15 text-primary-600 dark:text-primary-400">
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <circle cx="11" cy="11" r="7" />
            <path strokeLinecap="round" d="m21 21-4.3-4.3" />
          </svg>
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink">{item.title}</span>
        <span className="block truncate text-xs text-ink-400">
          {variant === "keyword" && item.matched_keywords && item.matched_keywords.length > 0
            ? `키워드: ${item.matched_keywords.join(", ")}`
            : item.agency}
        </span>
      </span>
    </a>
  );
}

/** 인앱 알림 벨 — 마감 임박 + 최근 키워드 새 공고. 미확인 수 뱃지(클라이언트 seen). */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [seen, setSeen] = useState<Set<string>>(() => new Set());
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    setSeen(loadSeen());
  }, []);

  const { data } = useQuery({
    queryKey: ["alerts"],
    queryFn: getAlerts,
    staleTime: 60 * 1000,
  });

  const reminders = data?.deadline_reminders ?? [];
  const hits = data?.keyword_hits ?? [];

  const allIds = useMemo(
    () => [
      ...reminders.map((r) => r.opportunity.opportunity_id),
      ...hits.map((h) => h.opportunity_id),
    ],
    [reminders, hits]
  );
  const unseenCount = useMemo(
    () => allIds.filter((id) => !seen.has(id)).length,
    [allIds, seen]
  );

  // 바깥 클릭 시 닫기
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && allIds.length > 0) {
      const merged = new Set(seen);
      allIds.forEach((id) => merged.add(id));
      setSeen(merged);
      saveSeen(merged);
    }
  }

  const empty = reminders.length === 0 && hits.length === 0;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        aria-label={mounted && unseenCount > 0 ? `알림 ${unseenCount}개` : "알림"}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-ink-600 transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
        {mounted && unseenCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unseenCount > 9 ? "9+" : unseenCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 max-h-[28rem] w-80 overflow-y-auto rounded-xl border border-surface-border bg-surface-card shadow-lg">
          <div className="sticky top-0 border-b border-surface-border bg-surface-card px-4 py-2.5 text-sm font-semibold text-ink">
            알림
          </div>
          {empty ? (
            <p className="px-4 py-10 text-center text-sm text-ink-400">새 알림이 없어요</p>
          ) : (
            <div className="divide-y divide-surface-border">
              {reminders.length > 0 && (
                <div className="p-2">
                  <p className="px-2 py-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
                    마감 임박 {reminders.length}
                  </p>
                  {reminders.map((r) => (
                    <AlertRow
                      key={`d-${r.opportunity.opportunity_id}`}
                      item={r.opportunity}
                      variant="deadline"
                      onClose={() => setOpen(false)}
                    />
                  ))}
                </div>
              )}
              {hits.length > 0 && (
                <div className="p-2">
                  <p className="px-2 py-1 text-xs font-semibold text-primary-700 dark:text-primary-300">
                    새 키워드 공고 {hits.length}
                  </p>
                  {hits.map((h) => (
                    <AlertRow
                      key={`k-${h.opportunity_id}`}
                      item={h}
                      variant="keyword"
                      onClose={() => setOpen(false)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
          <a
            href="/opportunities?tab=watch"
            onClick={() => setOpen(false)}
            className="block border-t border-surface-border px-4 py-2.5 text-center text-xs font-medium text-primary-600 dark:text-primary-400 hover:bg-surface"
          >
            키워드 워치 전체 보기 →
          </a>
        </div>
      )}
    </div>
  );
}
