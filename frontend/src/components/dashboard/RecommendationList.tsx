"use client";

import type { RecommendationItem } from "@/types/api";
import { RecommendationRow } from "./RecommendationRow";
import { InfoPopover } from "@/components/ui/InfoPopover";
import {
  SCORE_HELP_TITLE,
  SCORE_HELP_ARIA,
  ScoreHelpBody,
  FEASIBILITY_HELP_TITLE,
  FEASIBILITY_HELP_ARIA,
  FeasibilityHelpBody,
} from "./recommendationHelp";

interface RecommendationListProps {
  items: RecommendationItem[];
  mock?: boolean;
  /** 제공 시 각 행에 "진행 추가" 버튼 노출. */
  onAddToPipeline?: (item: RecommendationItem) => void;
  /** 제공 시 각 행에 "관심없음" 메뉴 노출. */
  onHide?: (item: RecommendationItem, reason: string) => void;
}

const headerLabel =
  "text-[10px] font-semibold uppercase tracking-wider text-ink-400";

/**
 * Console panel wrapping RecommendationRows: a sticky-feel column header row
 * (with help popovers on 적합도 / 수행가능성, reusing the card copy) over a
 * border-divided body. Column widths mirror RecommendationRow's grid.
 */
export function RecommendationList({
  items,
  mock = false,
  onAddToPipeline,
  onHide,
}: RecommendationListProps) {
  // 모든 행의 수행가능성이 비어 있으면 열 자체를 숨겨 빈 "—" 칸이 줄지어 보이는 것을 방지.
  const showFeasibility = items.some((i) => i.feasibility);
  const headerCols = showFeasibility
    ? "md:grid-cols-[minmax(0,1fr)_8.5rem_8rem_5rem_6rem_5.5rem]"
    : "md:grid-cols-[minmax(0,1fr)_8.5rem_5rem_6rem_5.5rem]";

  return (
    <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card shadow-sm">
      {/* Column header row (desktop only — rows are self-labelled on mobile) */}
      <div
        className={`hidden border-b border-surface-border bg-surface px-4 py-2.5 md:grid md:items-center md:gap-3 ${headerCols}`}
      >
        <span className={headerLabel}>공고</span>
        <div className="flex items-center gap-1">
          <span className={headerLabel}>적합도</span>
          <InfoPopover title={SCORE_HELP_TITLE} ariaLabel={SCORE_HELP_ARIA}>
            <ScoreHelpBody />
          </InfoPopover>
        </div>
        {showFeasibility && (
          <div className="flex items-center gap-1">
            <span className={headerLabel}>수행가능성</span>
            <InfoPopover title={FEASIBILITY_HELP_TITLE} ariaLabel={FEASIBILITY_HELP_ARIA}>
              <FeasibilityHelpBody />
            </InfoPopover>
          </div>
        )}
        <span className={headerLabel}>마감</span>
        <span className={headerLabel}>예산</span>
        <span className={`${headerLabel} text-right`}>액션</span>
      </div>

      {/* Body */}
      <div className="divide-y divide-surface-border">
        {items.map((item) => (
          <RecommendationRow
            key={item.opportunity_id}
            item={item}
            mock={mock}
            showFeasibility={showFeasibility}
            onAddToPipeline={onAddToPipeline ? () => onAddToPipeline(item) : undefined}
            onHide={onHide ? (reason) => onHide(item, reason) : undefined}
          />
        ))}
      </div>
    </div>
  );
}
