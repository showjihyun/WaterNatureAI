"use client";

import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { LoadingPage } from "@/components/ui/Spinner";
import { getFunnelMetrics, type FunnelMetrics } from "@/lib/api/metrics";

const pct = (n: number) => Math.round(n * 100);
const won = (n: number) => "₩" + n.toLocaleString("ko-KR");

function KpiCard({
  label,
  value,
  target,
  ratio,
  sub,
}: {
  label: string;
  value: string;
  target: string;
  ratio: number;
  sub?: string;
}) {
  const ok = ratio >= 1;
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
      <p className="text-xs text-ink-400">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold tabular-nums text-ink">
        {value}
        <span className="text-sm font-normal text-ink-400"> / {target}</span>
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-full rounded-full ${ok ? "bg-emerald-500" : "bg-primary-500"}`}
          style={{ width: `${Math.min(Math.max(ratio, 0) * 100, 100)}%` }}
        />
      </div>
      {sub && <p className="mt-1.5 text-[11px] text-ink-400">{sub}</p>}
    </div>
  );
}

const STAGES = [
  { key: "open", label: "열람", target: 0.4, pick: (d: FunnelMetrics) => d.opened },
  { key: "save", label: "관심 등록", target: 0.2, pick: (d: FunnelMetrics) => d.saved },
  { key: "participate", label: "참여/지원", target: 0.1, pick: (d: FunnelMetrics) => d.participated },
] as const;

export default function MetricsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["metrics", "funnel"],
    queryFn: getFunnelMetrics,
    retry: false,
  });

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">North Star 지표</h1>
        <p className="mt-0.5 text-sm text-ink-400">플랫폼 전체 퍼널 + 비즈니스 KPI · 운영자 전용</p>
      </div>

      {isLoading ? (
        <LoadingPage />
      ) : error ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          운영자 전용 지표입니다. <code className="font-mono">ADMIN_EMAILS</code>에 등록된 계정으로
          로그인하면 볼 수 있어요.
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* 비즈니스 KPI (90일 목표) */}
          <div className="grid gap-4 sm:grid-cols-3">
            <KpiCard
              label="유료 기업"
              value={`${data.paying_companies}社`}
              target={`${data.paying_target}社`}
              ratio={data.paying_companies / data.paying_target}
              sub={`전체 ${data.total_companies}社 · 온보딩 완료 ${data.ready_companies}社`}
            />
            <KpiCard
              label="MRR (월 반복 매출)"
              value={won(data.mrr)}
              target={won(data.mrr_target)}
              ratio={data.mrr / data.mrr_target}
              sub="활성·체험 구독 합계"
            />
            <KpiCard
              label="온보딩 완료율"
              value={`${data.total_companies ? pct(data.ready_companies / data.total_companies) : 0}%`}
              target="100%"
              ratio={data.total_companies ? data.ready_companies / data.total_companies : 0}
              sub={`가입 ${data.total_companies}社 → ready ${data.ready_companies}社`}
            />
          </div>

          {/* North Star 퍼널 */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="text-sm font-semibold text-ink-600">추천 퍼널 (플랫폼 전체)</h2>
              <span className="text-xs text-ink-400">
                추천{" "}
                <span className="font-display text-base font-bold tabular-nums text-ink">
                  {data.recommended.toLocaleString()}
                </span>
                건 기준
              </span>
            </div>
            <div className="space-y-3.5">
              {STAGES.map((s) => {
                const rate = data.rates[s.key] ?? 0;
                const onTrack = rate >= s.target;
                return (
                  <div key={s.key}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-sm font-medium text-ink">{s.label}</span>
                      <span className="font-display text-sm tabular-nums">
                        <span className="font-bold text-ink">{s.pick(data).toLocaleString()}</span>
                        <span className={onTrack ? "ml-1 text-emerald-600" : "ml-1 text-amber-600"}>
                          · {pct(rate)}%
                        </span>
                      </span>
                    </div>
                    <div className="relative mt-1 h-2.5 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className={`h-full rounded-full ${onTrack ? "bg-emerald-500" : "bg-amber-400"}`}
                        style={{ width: `${Math.min(pct(rate), 100)}%` }}
                      />
                      <div
                        className="absolute inset-y-0 w-0.5 bg-ink/40"
                        style={{ left: `${pct(s.target)}%` }}
                        aria-hidden="true"
                      />
                    </div>
                    <p className="mt-0.5 text-[11px] text-ink-400">
                      목표 {pct(s.target)}%{" "}
                      {onTrack ? (
                        <span className="font-medium text-emerald-600">✓ 달성</span>
                      ) : (
                        <span className="text-amber-600">· {Math.round((s.target - rate) * 100)}%p 부족</span>
                      )}
                    </p>
                  </div>
                );
              })}
            </div>
            <p className="mt-4 border-t border-surface-border pt-2.5 text-[11px] text-ink-400">
              목표선은 90일 성공 기준(열람 40% · 관심 20% · 참여 10%). 추천 대비 비율.
            </p>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
