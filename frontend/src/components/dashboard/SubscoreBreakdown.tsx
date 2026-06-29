"use client";

import type { RecommendationItem } from "@/types/api";

const DIMS = [
  { key: "tech", label: "기술", max: 30 },
  { key: "track", label: "실적", max: 25 },
  { key: "customer", label: "고객", max: 20 },
  { key: "industry", label: "산업", max: 15 },
  { key: "region", label: "지역", max: 10 },
] as const;

/**
 * 적합도 점수의 차원별 분해(기술·실적·고객·산업·지역) — "왜 이 점수인지" 설명.
 * 값은 매칭 엔진의 subscore(JSONB). 빈 차원은 0으로 표시.
 */
export function SubscoreBreakdown({
  subscore,
  className = "",
}: {
  subscore: NonNullable<RecommendationItem["subscore"]>;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-ink-400">
        적합도 구성
      </p>
      <div className="space-y-1">
        {DIMS.map((d) => {
          const v = subscore[d.key] ?? 0;
          const pct = Math.max(0, Math.min(100, Math.round((v / d.max) * 100)));
          return (
            <div key={d.key} className="flex items-center gap-2">
              <span className="w-7 shrink-0 text-[11px] text-ink-500">{d.label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-primary-400 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-9 shrink-0 text-right font-display text-[11px] tabular-nums text-ink-400">
                {v}
                <span className="text-ink-400">/{d.max}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
