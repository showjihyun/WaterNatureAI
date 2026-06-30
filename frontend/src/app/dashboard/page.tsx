"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { RecommendationCard } from "@/components/dashboard/RecommendationCard";
import { RecommendationList } from "@/components/dashboard/RecommendationList";
import { DeadlineReminders } from "@/components/dashboard/DeadlineReminders";
import { StatsPanel } from "@/components/dashboard/StatsPanel";
import { CollectionStatsPanel } from "@/components/dashboard/CollectionStatsPanel";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingPage } from "@/components/ui/Spinner";
import { ViewToggle } from "@/components/ui/ViewToggle";
import { SortControl } from "@/components/ui/SortControl";
import { useViewMode } from "@/lib/useViewMode";
import { sortRecommendations } from "@/lib/utils";
import { getTodayRecommendations } from "@/lib/api/recommendations";
import { getDashboardStats, getCollectionStats } from "@/lib/api/dashboard";
import { getCompanyProfile } from "@/lib/api/settings";
import { hideOpportunity, unhideOpportunity } from "@/lib/api/opportunities";
import type { SortKey, RecommendationItem } from "@/types/api";

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-surface-border bg-surface-card p-5 space-y-3 shadow-sm">
      <div className="flex justify-between">
        <div className="space-y-2">
          <div className="h-4 w-24 rounded bg-surface-muted" />
          <div className="h-5 w-64 rounded bg-surface-muted" />
        </div>
        <div className="h-8 w-16 rounded-lg bg-surface-muted" />
      </div>
      <div className="h-1.5 w-full rounded bg-surface-muted" />
      <div className="flex gap-2">
        <div className="h-6 w-20 rounded-full bg-surface-muted" />
        <div className="h-6 w-28 rounded-full bg-surface-muted" />
        <div className="h-6 w-24 rounded-full bg-surface-muted" />
      </div>
    </div>
  );
}

function DashboardContent() {
  const searchParams = useSearchParams();
  const isMock = searchParams.get("mock") === "1";
  const { mode, setMode } = useViewMode();
  const [sort, setSort] = useState<SortKey>("score");
  // 온보딩 직후 매칭이 백그라운드로 도는 동안 자동 새로고침 기준(최대 3분).
  const [analyzeStartedAt] = useState(() => Date.now());

  const {
    data: recommendations,
    isLoading: recsLoading,
    error: recsError,
    refetch: refetchRecs,
  } = useQuery({
    queryKey: ["recommendations", "today", isMock],
    queryFn: () => getTodayRecommendations(isMock),
    staleTime: 5 * 60 * 1000,
    // 추천 0건이면 매칭이 아직 진행 중일 수 있음 → 3분간 20초마다 자동 폴링(추천 뜨면 중단).
    refetchInterval: (query) => {
      if (isMock) return false;
      const recs = query.state.data;
      const empty = Array.isArray(recs) && recs.length === 0;
      return empty && Date.now() - analyzeStartedAt < 3 * 60 * 1000 ? 20000 : false;
    },
  });

  // Top-N recommendations are sorted client-side (no server round-trip).
  const sortedRecommendations = useMemo(
    () => (recommendations ? sortRecommendations(recommendations, sort) : recommendations),
    [recommendations, sort]
  );

  const {
    data: stats,
    isLoading: statsLoading,
  } = useQuery({
    queryKey: ["dashboard", "stats", isMock],
    queryFn: () => getDashboardStats(isMock),
    staleTime: 5 * 60 * 1000,
  });

  // 데이터 수집 현황(시장 통계) — 실데이터 전용(목 모드 제외).
  const { data: collectionStats } = useQuery({
    queryKey: ["dashboard", "collection"],
    queryFn: getCollectionStats,
    enabled: !isMock,
    staleTime: 5 * 60 * 1000,
  });

  // 수행 역량 미설정 감지 → 수행가능성(Go/No-Go) 컬럼이 비는 이유 안내.
  const { data: profile } = useQuery({
    queryKey: ["company", "profile"],
    queryFn: getCompanyProfile,
    enabled: !isMock,
    staleTime: 5 * 60 * 1000,
  });
  const needsCapability =
    !isMock &&
    !!profile &&
    profile.tech_level == null &&
    profile.max_project_budget == null &&
    (!profile.capable_categories || profile.capable_categories.length === 0) &&
    (!profile.capable_industries || profile.capable_industries.length === 0);
  const hasRecs = !!recommendations && recommendations.length > 0;

  // 추천 0건 분기: 프로필 미완성 vs (ready인데) 분석 중 vs 적합 공고 없음.
  const isReady = !isMock && profile?.onboarding_status === "ready";
  const noRecs =
    !recsLoading && !recsError && !!recommendations && recommendations.length === 0;
  const analyzing = isReady && noRecs && Date.now() - analyzeStartedAt < 3 * 60 * 1000;

  // 추천 피드백: '관심없음' → 숨김 + 실행취소 토스트.
  const queryClient = useQueryClient();
  const [hidden, setHidden] = useState<{ id: string; title: string } | null>(null);

  async function handleHide(item: RecommendationItem, reason: string) {
    try {
      await hideOpportunity(item.opportunity_id, reason, isMock);
      queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
      setHidden({ id: item.opportunity_id, title: item.title });
      window.setTimeout(
        () => setHidden((h) => (h?.id === item.opportunity_id ? null : h)),
        6000
      );
    } catch {
      // v1: 무시
    }
  }

  async function handleUndoHide() {
    if (!hidden) return;
    const id = hidden.id;
    setHidden(null);
    try {
      await unhideOpportunity(id, isMock);
      queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
    } catch {
      // 무시
    }
  }

  const today = new Date().toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink">오늘의 추천 공고</h1>
          <p className="mt-0.5 text-sm text-ink-400">{today}</p>
        </div>
        {isMock && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 dark:bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-700 dark:text-amber-300 ring-1 ring-inset ring-amber-600/20">
            <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 8 8">
              <circle cx="4" cy="4" r="3" />
            </svg>
            목(Mock) 데이터 미리보기
          </span>
        )}
      </div>

      {/* 마감 임박 — 관심/진행 공고 마감 리마인더(실데이터, 목 모드 제외) */}
      {!isMock && <DeadlineReminders />}

      {/* 역량 미설정 안내 — 수행가능성(Go/No-Go) 컬럼이 비는 이유 + CTA(리스트 바로 위 얇게 유지) */}
      {needsCapability && hasRecs && (
        <a
          href="/settings"
          className="mb-6 flex items-center gap-3 rounded-xl border border-primary-200 bg-primary-50 dark:bg-primary-500/15 px-4 py-3 transition-colors hover:bg-primary-100/60 dark:hover:bg-primary-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-100 dark:bg-primary-500/20 text-primary-700 dark:text-primary-300">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </span>
          <span className="min-w-0 flex-1 text-sm text-ink-600">
            <span className="font-semibold text-ink">수행 역량을 설정하면</span> 각 공고의 수행 가능성(Go/No-Go)을 자동으로 판단해 드려요.
          </span>
          <span className="shrink-0 text-sm font-medium text-primary-600 dark:text-primary-400">설정하기 →</span>
        </a>
      )}

      {/* Recommendations section */}
      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink-600">
            AI 맞춤 추천{" "}
            {recommendations && (
              <span className="ml-1.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-primary-100 dark:bg-primary-500/20 px-1.5 text-xs font-bold text-primary-700 dark:text-primary-300">
                {recommendations.length}
              </span>
            )}
          </h2>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            {recommendations && recommendations.length > 0 && (
              <SortControl value={sort} onChange={setSort} />
            )}
            <ViewToggle mode={mode} onChange={setMode} />
            <a
              href={`/opportunities${isMock ? "?mock=1" : ""}`}
              className="rounded-lg px-2 py-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-500/15 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
            >
              전체 보기 →
            </a>
          </div>
        </div>

        {recsLoading && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {recsError && (
          <Alert variant="error" onRetry={() => refetchRecs()}>
            추천 공고를 불러오는 중 오류가 발생했습니다.
          </Alert>
        )}

        {!recsLoading && !recsError && recommendations && recommendations.length === 0 && (
          !isReady ? (
            /* 프로필 미완성 — 온보딩으로 (목 모드 포함) */
            <EmptyState
              title="회사 프로필을 완성해 주세요"
              description="프로필을 등록하면 AI가 매일 우리 회사가 딸 수 있는 공고를 분석해 드려요."
              icon={
                <svg className="h-12 w-12" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="9" strokeOpacity="0.4" />
                  <circle cx="12" cy="12" r="5" strokeOpacity="0.6" />
                  <circle cx="12" cy="12" r="1.5" fill="currentColor" />
                </svg>
              }
              action={{ label: "프로필 작성하기", onClick: () => (window.location.href = "/onboarding") }}
            />
          ) : analyzing ? (
            /* ready인데 0건 + 분석 윈도우 내 — 매칭 진행 중(자동 새로고침) */
            <div className="rounded-xl border border-primary-200 bg-primary-50/60 dark:bg-primary-500/15 px-6 py-12 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-500/20">
                <svg className="h-6 w-6 animate-spin text-primary-600 dark:text-primary-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-ink">AI가 회사에 맞는 공고를 분석하고 있어요</h3>
              <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-600">
                보통 1~2분이면 끝나요. 이 화면은 자동으로 새로고침됩니다.
              </p>
              <a
                href="/opportunities"
                className="mt-5 inline-flex items-center gap-1 rounded-lg border border-primary-300 bg-surface-card px-3.5 py-2 text-sm font-medium text-primary-700 dark:text-primary-300 transition-colors hover:bg-primary-50 dark:hover:bg-primary-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
              >
                그동안 공고 탐색 둘러보기
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                </svg>
              </a>
            </div>
          ) : (
            /* ready인데 적합 공고 없음 — 직접 찾기 유도 */
            <div className="rounded-xl border border-surface-border bg-surface-card px-6 py-12 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-surface text-ink-400">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6" viewBox="0 0 24 24">
                  <circle cx="11" cy="11" r="7" />
                  <path strokeLinecap="round" d="m21 21-4.3-4.3" />
                </svg>
              </div>
              <h3 className="text-base font-semibold text-ink">지금 딱 맞는 공고가 없어요</h3>
              <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-600">
                새 공고가 올라오면 자동으로 분석해 알려드릴게요. 그동안 키워드 워치를 등록하거나 직접 탐색해 보세요.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <a
                  href="/opportunities?tab=watch"
                  className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-700 active:bg-primary-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
                >
                  키워드 워치 등록
                </a>
                <a
                  href="/opportunities"
                  className="inline-flex items-center gap-1 rounded-lg border border-surface-border bg-surface-card px-3.5 py-2 text-sm font-medium text-ink-600 transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
                >
                  공고 탐색
                </a>
              </div>
            </div>
          )
        )}

        {hidden && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-ink-700/10 bg-slate-900 px-3 py-2 text-sm text-white">
            <span className="truncate">
              ‘{hidden.title}’ 을(를) 추천에서 숨겼어요. 비슷한 공고를 덜 추천할게요.
            </span>
            <button onClick={handleUndoHide} className="ml-auto font-semibold text-primary-300 hover:underline">
              실행취소
            </button>
          </div>
        )}

        {!recsLoading && !recsError && sortedRecommendations && sortedRecommendations.length > 0 && (
          mode === "list" ? (
            <RecommendationList
              items={sortedRecommendations}
              mock={isMock}
              onHide={handleHide}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {sortedRecommendations.map((item) => (
                <RecommendationCard
                  key={item.opportunity_id}
                  item={item}
                  mock={isMock}
                  onHide={(reason) => handleHide(item, reason)}
                />
              ))}
            </div>
          )
        )}

        {!recsLoading && !recsError && hasRecs && (
          <a
            href={`/opportunities${isMock ? "?mock=1" : ""}`}
            className="mt-4 flex items-center justify-center gap-1.5 rounded-xl border border-dashed border-surface-border bg-surface-card py-4 text-sm font-medium text-ink-600 transition-colors hover:border-primary-300 hover:text-primary-600 dark:text-primary-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
          >
            전체 공고에서 더 많은 기회 탐색하기
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
            </svg>
          </a>
        )}
      </div>

      {/* Stats panel — 추천 퍼널(보조 지표). 핵심인 추천 리스트 다음에 배치. */}
      {stats && !statsLoading && (
        <div className="mt-8">
          <StatsPanel stats={stats} />
        </div>
      )}

      {/* 데이터 수집 현황 — 일/주/월/년 추세 + 소스/분야/예산/낙찰 분석(시장 통계). */}
      {!isMock && collectionStats && (
        <div className="mt-8">
          <CollectionStatsPanel stats={collectionStats} />
        </div>
      )}
    </AppShell>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<LoadingPage />}>
      <DashboardContent />
    </Suspense>
  );
}
