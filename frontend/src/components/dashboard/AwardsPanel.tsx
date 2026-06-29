"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAwards } from "@/lib/api/opportunities";
import { formatBudget } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingPage } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import type { AwardItem } from "@/types/api";

interface AwardsPanelProps {
  mock?: boolean;
}

const PAGE_SIZE = 20;

/** 낙찰 결과 — 기관/공고명 검색 + 낙찰 카드 목록 + 페이지네이션. */
export function AwardsPanel({ mock = false }: AwardsPanelProps) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  // 검색어 디바운스(OpportunityFilterBar 기관 입력과 동일하게 400ms).
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleSearch = useCallback((value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setQ(value.trim());
      setPage(1);
    }, 400);
  }, []);
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["awards", q, page, mock],
    queryFn: () => listAwards({ q: q || undefined, page }, mock),
    staleTime: 2 * 60 * 1000,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / (data.size || PAGE_SIZE))) : 1;

  return (
    <div>
      {/* Search */}
      <div className="mb-4">
        <label htmlFor="awards-search" className="sr-only">기관/공고명 검색</label>
        <input
          id="awards-search"
          type="text"
          defaultValue={q}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="기관/공고명 검색"
          className="h-9 w-full rounded-lg border border-surface-border bg-surface px-3 text-sm text-ink placeholder:text-ink-400 focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 sm:w-72"
        />
      </div>

      {isLoading && <LoadingPage />}
      {error && (
        <Alert variant="error" onRetry={() => refetch()}>
          낙찰 정보를 불러오지 못했습니다.
        </Alert>
      )}

      {!isLoading && !error && data && (
        <>
          {/* Total count */}
          <p className="mb-4 text-sm text-ink-400">
            총 <span className="font-medium text-ink">{data.total}</span>건
          </p>

          {data.items.length === 0 ? (
            <EmptyState
              title="아직 낙찰 데이터가 없어요"
              description="낙찰(결과) 수집이 실행되면 여기에 표시됩니다."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {data.items.map((item) => (
                <AwardCard key={item.id} item={item} />
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
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                이전
              </Button>
              <span className="text-sm text-ink-400">
                {data.page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={data.page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── award card ─────────────────────────────────────────────────────────────────

function AwardField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="shrink-0 text-xs font-medium text-ink-400">{label}</span>
      <span className="text-sm text-ink-600">{value}</span>
    </div>
  );
}

function AwardCard({ item }: { item: AwardItem }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        {item.category && <Badge color="gray">{item.category}</Badge>}
        <h3 className="font-semibold text-ink">{item.title ?? "제목 미상"}</h3>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
        <AwardField label="낙찰업체" value={item.winner_name ?? "-"} />
        <AwardField label="낙찰금액" value={formatBudget(item.award_amount)} />
        <AwardField
          label="낙찰률"
          value={item.award_rate != null ? `${item.award_rate}%` : "-"}
        />
        <AwardField
          label="참가"
          value={item.participant_count != null ? `${item.participant_count}개사` : "-"}
        />
        <AwardField label="수요기관" value={item.demand_agency ?? "-"} />
        <AwardField
          label="낙찰일"
          value={item.final_award_date ? item.final_award_date.replace(/-/g, ".") : "-"}
        />
      </div>
    </div>
  );
}
