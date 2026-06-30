"use client";

import { useState } from "react";
import type { CollectionStats, TrendPeriod, TrendPoint } from "@/types/api";
import { sourceLabel } from "@/lib/sourceLabel";

const PERIODS: { key: TrendPeriod; label: string; window: string }[] = [
  { key: "day", label: "일", window: "최근 14일" },
  { key: "week", label: "주", window: "최근 12주" },
  { key: "month", label: "월", window: "최근 12개월" },
  { key: "year", label: "년", window: "최근 5년" },
];

/** 금액 압축 표기(조/억/만원). */
function won(n: number | null | undefined): string {
  if (n == null) return "-";
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(1)}조원`;
  if (abs >= 1e8) return `${(n / 1e8).toFixed(1)}억원`;
  if (abs >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${Math.round(n).toLocaleString()}원`;
}

const num = (n: number) => n.toLocaleString("ko-KR");

/** 요약 타일 — 오늘/최근7일/누적/낙찰. */
function StatTile({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface px-3 py-2.5">
      <div className="text-[11px] text-ink-400">{label}</div>
      <div className={`mt-0.5 font-display text-xl font-bold tabular-nums ${accent ?? "text-ink"}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[10px] text-ink-400">{hint}</div>}
    </div>
  );
}

// 차트 카테고리 색(소스별·분야별) — 다크에서 토큰이 자동으로 밝아짐(globals .dark).
const CHART_BARS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"];

/** 가로 막대 한 줄(소스별/분야별/예산 분포 공용). */
function BarRow({
  label,
  value,
  max,
  right,
  barClass = "bg-primary-500/70",
}: {
  label: string;
  value: number;
  max: number;
  right: string;
  barClass?: string;
}) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="mb-0.5 flex items-baseline justify-between gap-2 text-xs">
        <span className="truncate text-ink-600">{label}</span>
        <span className="shrink-0 font-medium tabular-nums text-ink">{right}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={`h-full rounded-full transition-all ${barClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** 기간별 수집 추세 — 세로 막대. */
function TrendChart({ points }: { points: TrendPoint[] }) {
  const max = Math.max(1, ...points.map((p) => p.count));
  return (
    <div className="flex items-stretch gap-1">
      {points.map((p, i) => {
        const h = p.count > 0 ? Math.max(3, Math.round((p.count / max) * 100)) : 0;
        return (
          <div
            key={`${p.label}-${i}`}
            className="group flex min-w-0 flex-1 flex-col items-center"
            title={`${p.label} · ${num(p.count)}건`}
          >
            <div className="flex h-28 w-full items-end">
              <div
                className="mx-auto w-full max-w-[26px] rounded-t bg-primary-500/80 transition-all group-hover:bg-primary-600"
                style={{ height: `${h}%` }}
              />
            </div>
            <span className="mt-1 w-full truncate text-center text-[10px] text-ink-400">
              {p.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function CollectionStatsPanel({ stats }: { stats: CollectionStats }) {
  const [period, setPeriod] = useState<TrendPeriod>("day");
  const meta = PERIODS.find((p) => p.key === period)!;
  const points = stats.trends[period] ?? [];
  const periodTotal = points.reduce((s, p) => s + p.count, 0);

  const sourceTotal = stats.by_source.reduce((s, x) => s + x.count, 0) || 1;
  const srcMax = Math.max(1, ...stats.by_source.map((x) => x.count));
  const catMax = Math.max(1, ...stats.by_category.map((x) => x.count));
  const budgetMax = Math.max(1, ...stats.budget.buckets.map((x) => x.count));

  const asOf = (() => {
    try {
      return new Date(stats.as_of).toLocaleString("ko-KR", {
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  })();

  return (
    <section className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
      {/* 헤더 */}
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink-600">📊 데이터 수집 현황</h2>
        {asOf && <span className="text-[11px] text-ink-400">기준 {asOf}</span>}
      </div>

      {/* 요약 타일 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="오늘 신규"
          value={num(stats.summary.new_today)}
          hint="오늘 수집된 공고"
          accent="text-primary-600 dark:text-primary-400"
        />
        <StatTile label="최근 7일" value={num(stats.summary.new_7d)} hint="신규 수집" />
        <StatTile label="누적 공고" value={num(stats.summary.total)} hint="대표 공고 기준" />
        <StatTile label="누적 낙찰" value={num(stats.summary.awards_total)} hint="낙찰 결과" />
      </div>

      {/* 수집 추세 + 기간 토글 */}
      <div className="mt-6">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-ink-600">수집 추세</h3>
          <div
            role="group"
            aria-label="기간 선택"
            className="inline-flex rounded-lg border border-surface-border bg-surface p-0.5"
          >
            {PERIODS.map((p) => {
              const active = p.key === period;
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setPeriod(p.key)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 ${
                    active
                      ? "bg-surface-card text-primary-700 dark:text-primary-300 shadow-sm"
                      : "text-ink-500 hover:text-ink"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
        <p className="mb-2 text-[11px] text-ink-400">
          {meta.window} · 합계 <span className="font-medium text-ink-600">{num(periodTotal)}</span>건
        </p>
        <TrendChart points={points} />
      </div>

      {/* 분석 4블록 */}
      <div className="mt-6 grid gap-x-6 gap-y-5 sm:grid-cols-2">
        {/* 소스별 분포 */}
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-600">소스별 분포</h3>
          <div className="space-y-2">
            {stats.by_source.length === 0 ? (
              <p className="text-xs text-ink-400">수집 데이터가 없습니다.</p>
            ) : (
              stats.by_source.map((x, i) => (
                <BarRow
                  key={x.source}
                  label={sourceLabel(x.source)}
                  value={x.count}
                  max={srcMax}
                  right={`${num(x.count)} · ${Math.round((x.count / sourceTotal) * 100)}%`}
                  barClass={CHART_BARS[i % CHART_BARS.length]}
                />
              ))
            )}
          </div>
        </div>

        {/* 분야(업종)별 Top */}
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-600">분야(업종) Top</h3>
          <div className="space-y-2">
            {stats.by_category.length === 0 ? (
              <p className="text-xs text-ink-400">분류 정보가 없습니다.</p>
            ) : (
              stats.by_category.map((x, i) => (
                <BarRow
                  key={x.category}
                  label={x.category}
                  value={x.count}
                  max={catMax}
                  right={`${num(x.count)}건`}
                  barClass={CHART_BARS[i % CHART_BARS.length]}
                />
              ))
            )}
          </div>
        </div>

        {/* 예산 규모 분포 */}
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-600">예산 규모 분포</h3>
          <p className="mb-2 text-[11px] text-ink-400">
            합계 <span className="font-medium text-ink-600">{won(stats.budget.total)}</span> · 평균{" "}
            <span className="font-medium text-ink-600">{won(stats.budget.avg)}</span> ·{" "}
            {num(stats.budget.count_with_budget)}건
          </p>
          <div className="space-y-2">
            {stats.budget.buckets.map((b) => (
              <BarRow key={b.label} label={b.label} value={b.count} max={budgetMax} right={`${num(b.count)}건`} />
            ))}
          </div>
        </div>

        {/* 낙찰 통계 */}
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-600">낙찰 통계</h3>
          {stats.awards.count === 0 ? (
            <p className="text-xs text-ink-400">아직 수집된 낙찰 결과가 없습니다.</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <StatTile label="낙찰 건수" value={`${num(stats.awards.count)}건`} />
              <StatTile
                label="평균 낙찰률"
                value={stats.awards.avg_rate != null ? `${stats.awards.avg_rate}%` : "-"}
              />
              <StatTile label="평균 낙찰가" value={won(stats.awards.avg_amount)} />
              <StatTile label="낙찰가 합계" value={won(stats.awards.total_amount)} />
            </div>
          )}
        </div>
      </div>

      <p className="mt-4 border-t border-surface-border pt-2.5 text-[11px] text-ink-400">
        나라장터·K-Startup·NTIS 수집 기준. 추세는 신규 수집 시점(KST) 집계입니다.
      </p>
    </section>
  );
}
