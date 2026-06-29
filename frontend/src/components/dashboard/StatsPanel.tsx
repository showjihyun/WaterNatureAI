import type { StatsOut } from "@/types/api";

interface StatsPanelProps {
  stats: StatsOut;
}

const STAGES = [
  { key: "open", label: "열람", target: 0.4, pick: (s: StatsOut) => s.opened },
  { key: "save", label: "관심 등록", target: 0.2, pick: (s: StatsOut) => s.saved },
  { key: "participate", label: "참여/지원", target: 0.1, pick: (s: StatsOut) => s.participated },
] as const;

/** 퍼널 한 단계 — 추천 대비 전환율 막대 + 목표선(North Star) + 달성 여부. */
function FunnelStage({
  label,
  count,
  rate,
  target,
  showRate,
}: {
  label: string;
  count: number;
  rate: number;
  target: number;
  showRate: boolean;
}) {
  const pct = Math.round(rate * 100);
  const onTrack = rate >= target;
  const gap = Math.round((target - rate) * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-ink">{label}</span>
        <span className="font-display tabular-nums">
          <span className="text-base font-bold text-ink">{count}</span>
          {showRate && (
            <span className={onTrack ? "ml-1 text-xs text-emerald-600 dark:text-emerald-300" : "ml-1 text-xs text-amber-600 dark:text-amber-300"}>
              · {pct}%
            </span>
          )}
        </span>
      </div>
      <div className="relative mt-1 h-2 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={`h-full rounded-full transition-all ${onTrack ? "bg-emerald-500" : "bg-amber-400"}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
        {/* 목표선 */}
        <div
          className="absolute inset-y-0 w-0.5 bg-ink/40"
          style={{ left: `${Math.min(target * 100, 100)}%` }}
          aria-hidden="true"
        />
      </div>
      {showRate && (
        <p className="mt-0.5 text-[11px] text-ink-400">
          목표 {Math.round(target * 100)}%{" "}
          {onTrack ? (
            <span className="font-medium text-emerald-600 dark:text-emerald-300">✓ 달성</span>
          ) : (
            <span className="text-amber-600 dark:text-amber-300">· {gap}%p 부족</span>
          )}
        </p>
      )}
    </div>
  );
}

export function StatsPanel({ stats }: StatsPanelProps) {
  const showRate = stats.recommended > 0;
  // 코칭 문구는 어떤 활동도 없을 때만(관심·참여가 있으면 모순이므로 제외).
  const noEngagement =
    stats.recommended > 0 &&
    stats.opened === 0 &&
    stats.saved === 0 &&
    stats.participated === 0;

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink-600">추천 퍼널</h2>
        <span className="text-xs text-ink-400">
          추천{" "}
          <span className="font-display text-base font-bold tabular-nums text-ink">
            {stats.recommended}
          </span>
          건 기준
        </span>
      </div>

      {noEngagement && (
        <p className="mb-3 rounded-lg bg-surface px-3 py-2 text-xs text-ink-500">
          아직 활동이 없어요. 추천 공고를 열람·관심 등록하면 전환율이 여기에 쌓입니다.
        </p>
      )}

      <div className="space-y-3">
        {STAGES.map((s) => (
          <FunnelStage
            key={s.key}
            label={s.label}
            count={s.pick(stats)}
            rate={stats.rates[s.key] ?? 0}
            target={s.target}
            showRate={showRate}
          />
        ))}
      </div>

      <p className="mt-4 border-t border-surface-border pt-2.5 text-[11px] text-ink-400">
        목표선은 서비스 기준(열람 40% · 관심 20% · 참여 10%)입니다.
      </p>
    </div>
  );
}
