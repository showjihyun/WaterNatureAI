"use client";

import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { RecommendationCard } from "@/components/dashboard/RecommendationCard";
import { RecommendationList } from "@/components/dashboard/RecommendationList";
import { KeywordWatchPanel } from "@/components/watch/KeywordWatchPanel";
import { AwardsPanel } from "@/components/dashboard/AwardsPanel";
import { EmptyState } from "@/components/ui/EmptyState";
import { Alert } from "@/components/ui/Alert";
import { LoadingPage } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { ViewToggle } from "@/components/ui/ViewToggle";
import { SortControl } from "@/components/ui/SortControl";
import { cn } from "@/lib/utils";
import { useViewMode } from "@/lib/useViewMode";
import { listOpportunities } from "@/lib/api/opportunities";
import { OpportunityFilterBar, countActiveFilters } from "@/components/dashboard/OpportunityFilters";
import type { OpportunityFilters, SortKey } from "@/types/api";

type ExploreTab = "all" | "watch" | "awards";

const DEFAULT_FILTERS: OpportunityFilters = {
  page: 1,
  size: 20,
  sort: "score",
};

function OpportunitiesContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const isMock = searchParams.get("mock") === "1";
  const { mode, setMode } = useViewMode();

  const initialTab = searchParams.get("tab");
  const [tab, setTab] = useState<ExploreTab>(
    initialTab === "watch" ? "watch" : initialTab === "awards" ? "awards" : "all"
  );

  function switchTab(next: ExploreTab) {
    setTab(next);
    const qs = new URLSearchParams(searchParams.toString());
    if (next === "watch" || next === "awards") qs.set("tab", next);
    else qs.delete("tab");
    const s = qs.toString();
    router.replace(s ? `/opportunities?${s}` : "/opportunities", { scroll: false });
  }

  const [filters, setFilters] = useState<OpportunityFilters>(DEFAULT_FILTERS);

  const sort: SortKey = filters.sort ?? "score";

  function handleSortChange(next: SortKey) {
    setFilters((prev) => ({ ...prev, sort: next, page: 1 }));
  }

  function handleFilterChange(patch: Partial<OpportunityFilters>) {
    setFilters((prev) => ({ ...prev, ...patch, page: 1 }));
  }

  function handleReset() {
    setFilters(DEFAULT_FILTERS);
  }

  const activeCount = countActiveFilters(filters);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["opportunities", filters, isMock],
    queryFn: () => listOpportunities(filters, isMock),
    staleTime: 2 * 60 * 1000,
  });

  return (
    <AppShell>
      {/* Page header */}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-ink">공고 탐색</h1>
        <p className="mt-0.5 text-sm text-ink-400">
          공고를 필터로 탐색하거나, 키워드 워치로 모아 보세요
        </p>
      </div>

      {/* Tabs: 전체 공고 / 키워드 워치 */}
      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-surface-border" role="tablist" aria-label="공고 탐색 보기">
        {([["all", "전체 공고"], ["watch", "키워드 워치"], ["awards", "낙찰 결과"]] as const).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            id={`tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`tabpanel-${key}`}
            onClick={() => switchTab(key)}
            className={cn(
              "-mb-px whitespace-nowrap rounded-t border-b-2 px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
              tab === key
                ? "border-primary-600 text-primary-700 dark:text-primary-300"
                : "border-transparent text-ink-400 hover:border-surface-border hover:text-ink-600"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "watch" ? (
        <div id="tabpanel-watch" role="tabpanel" aria-labelledby="tab-watch">
          <KeywordWatchPanel />
        </div>
      ) : tab === "awards" ? (
        <div id="tabpanel-awards" role="tabpanel" aria-labelledby="tab-awards">
          <AwardsPanel mock={isMock} />
        </div>
      ) : (
        <div id="tabpanel-all" role="tabpanel" aria-labelledby="tab-all">
      {/* Filter bar */}
      <div className="mb-4">
        <OpportunityFilterBar
          filters={filters}
          onChange={handleFilterChange}
          onReset={handleReset}
          activeCount={activeCount}
        />
      </div>

      {/* Results header: total count + sort/view controls */}
      {!isLoading && !error && data && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-sm text-ink-400">
            총 <span className="font-medium text-ink">{data.total}</span>건
            {activeCount > 0 && (
              <span className="ml-1 text-primary-600 dark:text-primary-400 font-medium">
                (필터 {activeCount}개 적용)
              </span>
            )}
          </p>
          {data.items.length > 0 && (
            <div className="flex items-center gap-2">
              <SortControl value={sort} onChange={handleSortChange} />
              <ViewToggle mode={mode} onChange={setMode} />
            </div>
          )}
        </div>
      )}

      {/* Loading / Error */}
      {isLoading && <LoadingPage />}
      {error && (
        <Alert variant="error" onRetry={() => refetch()}>
          공고를 불러오는 중 오류가 발생했습니다.
        </Alert>
      )}

      {/* Items */}
      {!isLoading && !error && data && (
        <>
          {data.items.length === 0 ? (
            <EmptyState
              title="조건에 맞는 공고가 없어요"
              description="필터를 완화해 보세요."
              action={{ label: "필터 초기화", onClick: handleReset }}
            />
          ) : mode === "list" ? (
            <RecommendationList items={data.items} mock={isMock} />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {data.items.map((item) => (
                <RecommendationCard key={item.opportunity_id} item={item} mock={isMock} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {data.total > data.size && (
            <div className="mt-6 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={data.page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                이전
              </Button>
              <span className="text-sm text-ink-400">
                {data.page} / {Math.ceil(data.total / data.size)}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={data.page >= Math.ceil(data.total / data.size)}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                다음
              </Button>
            </div>
          )}
        </>
      )}
        </div>
      )}
    </AppShell>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<LoadingPage />}>
      <OpportunitiesContent />
    </Suspense>
  );
}
