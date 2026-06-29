"use client";

import type { RecommendationItem } from "@/types/api";
import { formatBudget } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import { ScoreBadge } from "./ScoreBadge";
import { DaysBadge } from "./DaysBadge";
import { SaveButton } from "@/components/ui/SaveButton";
import { FeasibilityBadge } from "./FeasibilityBadge";
import { useRecommendationActions } from "./useRecommendationActions";
import { HideMenu } from "./HideMenu";
import { SubscoreBreakdown } from "./SubscoreBreakdown";
import {
  SCORE_HELP_TITLE,
  SCORE_HELP_ARIA,
  ScoreHelpBody,
  FEASIBILITY_HELP_TITLE,
  FEASIBILITY_HELP_ARIA,
  FeasibilityHelpBody,
} from "./recommendationHelp";
import { InfoPopover } from "@/components/ui/InfoPopover";

interface RecommendationCardProps {
  item: RecommendationItem;
  mock?: boolean;
  /** 제공 시 "관심없음" 메뉴 노출(추천 피드백). */
  onHide?: (reason: string) => void;
}

export function RecommendationCard({ item, mock = false, onHide }: RecommendationCardProps) {
  const { saved, savingInProgress, handleSaveToggle, handleViewSource } =
    useRecommendationActions(item, mock);
  const displayedReasons = item.reasons.slice(0, 3);

  return (
    <article className="group flex flex-col rounded-xl border border-surface-border bg-surface-card shadow-sm transition-shadow hover:shadow-md overflow-hidden">
      {/* Card header */}
      <div className="px-5 pt-5 pb-3 border-b border-surface-border">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {/* Eyebrow: Agency + Category */}
            <div className="flex flex-wrap items-center gap-1.5 mb-2">
              {item.agency && (
                <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
                  {item.agency}
                </span>
              )}
              {item.agency && item.category && (
                <span className="text-ink-400 text-xs">·</span>
              )}
              {item.category && (
                <span className="text-xs text-ink-400 uppercase tracking-wide">
                  {item.category}
                </span>
              )}
            </div>
            {/* Title */}
            <h3 className="text-sm font-semibold text-ink leading-snug line-clamp-2">
              {item.title}
            </h3>
          </div>
          {/* D-day badge */}
          <DaysBadge dDay={item.d_day} deadline={item.deadline} className="shrink-0" />
        </div>
      </div>

      {/* Card body */}
      <div className="px-5 py-3 flex-1">
        {/* Readout row: Score + Feasibility + Budget */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <InfoPopover title={SCORE_HELP_TITLE} ariaLabel={SCORE_HELP_ARIA}>
                <ScoreHelpBody />
              </InfoPopover>
              <ScoreBadge score={item.score} showBar />
            </div>
            {item.feasibility && (
              <div className="flex items-center gap-1.5">
                <InfoPopover title={FEASIBILITY_HELP_TITLE} ariaLabel={FEASIBILITY_HELP_ARIA}>
                  <FeasibilityHelpBody />
                </InfoPopover>
                <FeasibilityBadge feasibility={item.feasibility} compact />
              </div>
            )}
          </div>
          <div className="text-right">
            <span className="font-display tabular-nums text-sm font-semibold text-ink">
              {formatBudget(item.budget_amount)}
            </span>
            {item.source && (
              <div className="text-xs text-ink-400 mt-0.5">{sourceLabel(item.source)}</div>
            )}
          </div>
        </div>

        {/* Reasons — 매칭 점수 산출 근거(규칙 템플릿; LLM 키 설정 시 상위 일부만 AI가 다듬음) */}
        {displayedReasons.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-ink-400 uppercase tracking-wide">
              추천 근거
            </p>
            <ul className="space-y-1">
              {displayedReasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-ink-600">
                  <svg className="mt-0.5 h-3 w-3 shrink-0 text-primary-500" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1zm3.707 5.293a1 1 0 0 0-1.414 0L7 9.586 5.707 8.293a1 1 0 0 0-1.414 1.414l2 2a1 1 0 0 0 1.414 0l4-4a1 1 0 0 0 0-1.414z" />
                  </svg>
                  <span className="leading-snug">{reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 적합도 구성(차원별 분해) — 왜 이 점수인지 */}
        {item.subscore && (
          <SubscoreBreakdown
            subscore={item.subscore}
            className="mt-3 border-t border-surface-border pt-3"
          />
        )}

        {/* 리스크/참고 한 줄 */}
        {item.risk && (
          <div className="mt-3 flex items-start gap-1.5 rounded-lg bg-amber-50 dark:bg-amber-500/15/70 px-2.5 py-1.5 text-xs text-amber-800 dark:text-amber-300">
            <svg className="mt-0.5 h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span className="leading-snug">{item.risk}</span>
          </div>
        )}
      </div>

      {/* Card footer actions */}
      <div className="flex items-center justify-between gap-2 px-5 py-3 border-t border-surface-border bg-surface">
        <SaveButton saved={saved} onClick={handleSaveToggle} disabled={savingInProgress} showLabel />

        <div className="flex items-center gap-1.5">
          {onHide && <HideMenu onHide={onHide} />}
          <button
            onClick={handleViewSource}
            disabled={!item.detail_url}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 active:bg-primary-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            원문 보기
          <svg
            className="h-3 w-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
          </button>
        </div>
      </div>
    </article>
  );
}
