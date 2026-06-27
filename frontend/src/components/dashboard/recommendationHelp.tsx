import type { ReactNode } from "react";

/**
 * Shared help copy for the "적합도" (score) and "수행 가능성" (feasibility)
 * metrics, reused by both the card readout and the list column headers so the
 * explanation stays identical in every presentation.
 */

export const SCORE_HELP_TITLE = "적합도란?";
export const SCORE_HELP_ARIA = "적합도 도움말";

export function ScoreHelpBody(): ReactNode {
  return (
    <ul className="space-y-1.5 list-none">
      <li>우리 회사 역량과 공고의 일치도를 0~100으로 점수화한 값이에요.</li>
      <li>
        <span className="font-medium text-gray-700">평가 항목:</span> 기술 적합(의미 유사도 + 키워드), 산업 적합, 지역 적합 등을 종합합니다.
      </li>
      <li>35점 이상인 공고만 추천에 노출돼요. 점수가 높을수록 우리 회사에 더 맞는 사업입니다.</li>
    </ul>
  );
}

export const FEASIBILITY_HELP_TITLE = "수행 가능성이란?";
export const FEASIBILITY_HELP_ARIA = "수행 가능성 도움말";

export function FeasibilityHelpBody(): ReactNode {
  return (
    <ul className="space-y-1.5 list-none">
      <li>설정한 &apos;수행 역량&apos;으로 이 사업을 실제로 감당할 수 있는지 판단해요.</li>
      <li>🟢 수행 가능 · 🟡 검토 필요 · 🔴 수행 어려움</li>
      <li>
        <span className="font-medium text-gray-700">기준</span> — 수행 유형 일치 / 사업 규모(예산 vs 감당 가능 최대 규모) / 기술 수준.
      </li>
      <li>기준 값은 [설정 &gt; 수행 역량]에서 바꿀 수 있어요.</li>
    </ul>
  );
}
