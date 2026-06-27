"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { RecommendationList } from "@/components/dashboard/RecommendationList";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { getSavedOpportunities } from "@/lib/api/recommendations";
import { addPursuit } from "@/lib/api/pursuits";
import type { RecommendationItem } from "@/types/api";

function SkeletonRows() {
  return (
    <div className="divide-y divide-surface-border overflow-hidden rounded-xl border border-surface-border bg-surface-card shadow-sm">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse px-4 py-4">
          <div className="mb-2 h-3 w-1/4 rounded bg-gray-100" />
          <div className="h-4 w-2/3 rounded bg-gray-100" />
        </div>
      ))}
    </div>
  );
}

export default function SavedPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["recommendations", "saved"],
    queryFn: getSavedOpportunities,
    staleTime: 60 * 1000,
  });

  const count = data?.length ?? 0;
  const [addedTitle, setAddedTitle] = useState<string | null>(null);

  // 성공 토스트 자동 해제 — 언마운트 시 타이머 정리(setState 누수 방지).
  useEffect(() => {
    if (!addedTitle) return;
    const timer = window.setTimeout(() => setAddedTitle(null), 4000);
    return () => window.clearTimeout(timer);
  }, [addedTitle]);

  async function handleAddToPipeline(item: RecommendationItem) {
    try {
      await addPursuit(item.opportunity_id);
      queryClient.invalidateQueries({ queryKey: ["pursuits"] });
      setAddedTitle(item.title);
    } catch {
      // v1: 무시(중복 추가는 서버에서 멱등 처리)
    }
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">관심 공고</h1>
        <p className="mt-0.5 text-sm text-ink-400">
          저장한 공고를 모아봤어요
          {count > 0 && ` · 총 ${count}건 (최근 저장순)`}
        </p>
      </div>

      {addedTitle && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          <span>✓ &lsquo;{addedTitle}&rsquo; 을(를) 진행 관리에 추가했어요.</span>
          <a href="/pipeline" className="ml-auto font-medium underline">
            진행 관리 보기 →
          </a>
        </div>
      )}

      {isLoading && <SkeletonRows />}

      {isError && (
        <Alert variant="error" onRetry={() => refetch()}>
          관심 공고를 불러오는 중 오류가 발생했습니다.
        </Alert>
      )}

      {!isLoading && !isError && data && count === 0 && (
        <EmptyState
          title="아직 관심 공고가 없습니다"
          description="대시보드나 공고 탐색에서 ♥ 버튼을 눌러 공고를 저장하면 여기에 모입니다."
          icon={
            <svg className="h-12 w-12" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
              />
            </svg>
          }
          action={{ label: "공고 탐색하기", onClick: () => (window.location.href = "/opportunities") }}
        />
      )}

      {!isLoading && !isError && data && count > 0 && (
        <RecommendationList items={data} onAddToPipeline={handleAddToPipeline} />
      )}
    </AppShell>
  );
}
