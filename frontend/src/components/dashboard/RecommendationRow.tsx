"use client";

import type { RecommendationItem } from "@/types/api";
import { formatBudget, formatScore, cn } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import { FeasibilityBadge } from "./FeasibilityBadge";
import { HideMenu } from "./HideMenu";
import { SubscoreBreakdown } from "./SubscoreBreakdown";
import { InfoPopover } from "@/components/ui/InfoPopover";
import { SaveButton } from "@/components/ui/SaveButton";
import { DaysBadge } from "@/components/ui/DaysBadge";
import { useRecommendationActions } from "./useRecommendationActions";

interface RecommendationRowProps {
  item: RecommendationItem;
  mock?: boolean;
  /** 제공 시 액션 영역에 "진행 추가" 버튼 노출(관심 공고함 → 파이프라인 진입). */
  onAddToPipeline?: () => void;
  /** 제공 시 "관심없음" 메뉴 노출(추천 피드백). reason 코드를 전달. */
  onHide?: (reason: string) => void;
  /** false면 수행가능성 칸을 렌더하지 않음(List가 전체 행에 feasibility가 없을 때 전달). */
  showFeasibility?: boolean;
}

/**
 * Console table row presentation of a single recommendation. Same information
 * and actions as RecommendationCard (via the shared useRecommendationActions
 * hook), laid out as aligned columns on desktop and a 2-line stack on mobile.
 * Column widths mirror the header row in RecommendationList.
 */
export function RecommendationRow({
  item,
  mock = false,
  onAddToPipeline,
  onHide,
  showFeasibility = true,
}: RecommendationRowProps) {
  const { saved, savingInProgress, handleSaveToggle, handleViewSource } =
    useRecommendationActions(item, mock);

  return (
    <div
      className={cn(
        "group px-4 py-3 transition-colors hover:bg-surface md:grid md:items-center md:gap-3",
        showFeasibility
          ? "md:grid-cols-[minmax(0,1fr)_8.5rem_8rem_5rem_6rem_5.5rem]"
          : "md:grid-cols-[minmax(0,1fr)_8.5rem_5rem_6rem_5.5rem]"
      )}
    >
      {/* 공고: title + agency/category eyebrow (lead column) */}
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          {item.agency && (
            <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
              {item.agency}
            </span>
          )}
          {item.agency && item.category && <span className="text-xs text-ink-400">·</span>}
          {item.category && (
            <span className="text-xs uppercase tracking-wide text-ink-400">{item.category}</span>
          )}
        </div>
        <h3 className="truncate text-sm font-semibold leading-snug text-ink">{item.title}</h3>
        {item.matched_keywords && item.matched_keywords.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {item.matched_keywords.map((kw) => (
              <span
                key={kw}
                className="inline-flex items-center gap-0.5 rounded bg-primary-50 dark:bg-primary-500/15 px-1.5 py-0.5 text-[10px] font-medium text-primary-700 dark:text-primary-300 ring-1 ring-inset ring-primary-600/10"
              >
                <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="11" cy="11" r="7" />
                  <path strokeLinecap="round" d="m21 21-4.3-4.3" />
                </svg>
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 적합도: score readout + cyan strength bar */}
      <div className="mt-2 flex items-center gap-2 md:mt-0">
        <span className="inline-flex md:hidden mr-1 text-[10px] font-medium uppercase tracking-wide text-ink-400">
          적합도
        </span>
        <span className="font-display tabular-nums text-base font-bold leading-none text-ink">
          {formatScore(item.score)}
        </span>
        {item.score != null && (
          <div className="h-2 w-16 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-primary-500 transition-all"
              style={{ width: `${Math.min(item.score, 100)}%` }}
            />
          </div>
        )}
        {item.subscore && (
          <InfoPopover title="적합도 구성" ariaLabel="적합도 구성 보기">
            <SubscoreBreakdown subscore={item.subscore} />
            {item.risk && (
              <p className="mt-2 flex items-start gap-1 text-[11px] leading-snug text-amber-700 dark:text-amber-300">
                <span aria-hidden="true">⚠</span>
                <span>{item.risk}</span>
              </p>
            )}
          </InfoPopover>
        )}
      </div>

      {/* 수행가능성: badge or blank (모든 행에 값이 없으면 List가 칸 자체를 숨김) */}
      {showFeasibility && (
        <div className="mt-2 md:mt-0">
          {item.feasibility ? (
            <FeasibilityBadge feasibility={item.feasibility} compact />
          ) : (
            <span className="hidden text-xs text-ink-400 md:inline">—</span>
          )}
        </div>
      )}

      {/* mobile-only readout row groups the remaining columns inline */}
      <div className="mt-2 flex items-center gap-4 md:contents">
        {/* 마감: D-day */}
        <div className="md:flex md:flex-col md:items-start">
          <span className="inline-flex md:hidden mr-1 text-[10px] font-medium uppercase tracking-wide text-ink-400">
            마감
          </span>
          <DaysBadge dDay={item.d_day} />
        </div>

        {/* 예산 */}
        <div className="md:text-left">
          <span className="font-display tabular-nums text-sm font-semibold text-ink">
            {formatBudget(item.budget_amount)}
          </span>
          {item.source && (
            <div className="hidden text-xs text-ink-400 md:block">{sourceLabel(item.source)}</div>
          )}
        </div>

        {/* 액션: save toggle + view source */}
        <div className="ml-auto flex items-center gap-1.5 md:ml-0">
          {onAddToPipeline && (
            <button
              onClick={onAddToPipeline}
              aria-label="진행 관리에 추가"
              title="진행 관리에 추가"
              className="inline-flex h-9 items-center gap-0.5 rounded-lg border border-surface-border px-2 text-[11px] font-medium text-ink-600 transition-colors hover:border-primary-300 hover:bg-primary-50 dark:bg-primary-500/15 hover:text-primary-700 dark:text-primary-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
            >
              <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              진행
            </button>
          )}
          {onHide && <HideMenu onHide={onHide} />}
          <SaveButton saved={saved} onClick={handleSaveToggle} disabled={savingInProgress} />
          <button
            onClick={handleViewSource}
            disabled={!item.detail_url}
            className="inline-flex h-9 items-center gap-1 rounded-lg bg-primary-600 px-2.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 active:bg-primary-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="원문 보기"
          >
            원문
            <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
