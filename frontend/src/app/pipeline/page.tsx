"use client";

import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { PursuitCard } from "@/components/pipeline/PursuitCard";
import { getPursuits, PURSUIT_STAGES, type PursuitStage } from "@/lib/api/pursuits";

export default function PipelinePage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["pursuits"],
    queryFn: getPursuits,
    staleTime: 30 * 1000,
  });

  const total = data?.length ?? 0;
  const byStage = (stage: PursuitStage) => (data ?? []).filter((p) => p.stage === stage);

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">진행 관리</h1>
        <p className="mt-0.5 text-sm text-ink-400">
          추적 중인 공고를 단계별로 관리하세요
          {total > 0 && ` · ${total}건`}
        </p>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {PURSUIT_STAGES.map((s) => (
            <div key={s.key} className="rounded-xl border border-surface-border bg-surface p-3">
              <div className="mb-3 h-4 w-16 animate-pulse rounded bg-gray-200" />
              <div className="h-24 animate-pulse rounded-lg bg-surface-card" />
            </div>
          ))}
        </div>
      )}

      {isError && (
        <Alert variant="error" onRetry={() => refetch()}>
          진행 목록을 불러오는 중 오류가 발생했습니다.
        </Alert>
      )}

      {!isLoading && !isError && total === 0 && (
        <EmptyState
          title="진행 중인 공고가 없습니다"
          description="관심 공고에서 '진행 추가'를 누르면 검토중·준비중·제출·완료 단계로 관리할 수 있어요."
          icon={
            <svg className="h-12 w-12" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          }
          action={{ label: "관심 공고 보기", onClick: () => (window.location.href = "/saved") }}
        />
      )}

      {!isLoading && !isError && total > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {PURSUIT_STAGES.map((s) => {
            const items = byStage(s.key);
            return (
              <section
                key={s.key}
                aria-label={s.label}
                className="rounded-xl border border-surface-border bg-surface p-3"
              >
                <div className="mb-3 flex items-center justify-between px-1">
                  <span className="text-sm font-semibold text-ink-600">{s.label}</span>
                  <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full border border-surface-border bg-surface-card px-1.5 text-xs font-bold text-ink-400">
                    {items.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {items.length === 0 ? (
                    <p className="py-6 text-center text-xs text-ink-400">이 단계의 공고가 없습니다</p>
                  ) : (
                    items.map((p) => (
                      <PursuitCard key={p.opportunity.opportunity_id} item={p} />
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
