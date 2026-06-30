"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RecommendationList } from "@/components/dashboard/RecommendationList";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { ApiError } from "@/lib/api/client";
import { getWatches, addWatch, removeWatch, getWatchMatches } from "@/lib/api/watches";
import { addPursuit } from "@/lib/api/pursuits";
import type { RecommendationItem } from "@/types/api";

function errMsg(e: unknown): string {
  if (
    e instanceof ApiError &&
    e.detail &&
    typeof e.detail === "object" &&
    "detail" in e.detail
  ) {
    return String((e.detail as { detail: unknown }).detail);
  }
  return "키워드를 추가하지 못했습니다.";
}

function SkeletonRows() {
  return (
    <div className="divide-y divide-surface-border overflow-hidden rounded-xl border border-surface-border bg-surface-card shadow-sm">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="animate-pulse px-4 py-4">
          <div className="mb-2 h-3 w-1/4 rounded bg-surface-muted" />
          <div className="h-4 w-2/3 rounded bg-surface-muted" />
        </div>
      ))}
    </div>
  );
}

const watchIcon = (
  <svg className="h-12 w-12" fill="none" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" />
  </svg>
);

/**
 * 키워드 워치 패널 — '공고 탐색'의 [키워드 워치] 탭 본문. 키워드(저장 검색) 칩 관리 +
 * 제목·기관·내용에 키워드가 들어간 공고 피드. AppShell/페이지 헤더는 부모가 제공.
 */
export function KeywordWatchPanel() {
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [addedTitle, setAddedTitle] = useState<string | null>(null);

  const { data: watches, isLoading: watchesLoading } = useQuery({
    queryKey: ["watches"],
    queryFn: getWatches,
  });
  const {
    data: matches,
    isLoading: matchesLoading,
    isError,
  } = useQuery({
    queryKey: ["watches", "matches"],
    queryFn: getWatchMatches,
    staleTime: 60 * 1000,
  });

  const hasKeywords = (watches?.length ?? 0) > 0;
  const matchCount = matches?.length ?? 0;

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ["watches"] });
    queryClient.invalidateQueries({ queryKey: ["watches", "matches"] });
    queryClient.invalidateQueries({ queryKey: ["alerts"] });
  }

  const addMutation = useMutation({
    mutationFn: addWatch,
    onSuccess: () => {
      setInput("");
      setError(null);
      invalidateAll();
    },
    onError: (e) => setError(errMsg(e)),
  });

  const removeMutation = useMutation({
    mutationFn: removeWatch,
    onSuccess: invalidateAll,
  });

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const kw = input.trim();
    if (kw.length < 2) {
      setError("키워드는 2자 이상 입력하세요.");
      return;
    }
    addMutation.mutate(kw);
  }

  // 토스트 자동 해제 — 언마운트/갱신 시 타이머 정리(cleanup)
  useEffect(() => {
    if (!addedTitle) return;
    const t = window.setTimeout(() => setAddedTitle(null), 4000);
    return () => window.clearTimeout(t);
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
    <div>
      <p className="mb-4 text-sm text-ink-400">
        관심 키워드를 등록하면 AI 추천과 별개로, <span className="font-medium text-ink-700">제목·기관·내용</span>에
        그 키워드가 들어간 공고를 모아드려요.
      </p>

      {/* 키워드 관리 */}
      <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
        <form onSubmit={handleAdd} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              if (error) setError(null);
            }}
            placeholder="예: 수처리, 막여과, 데이터 구축"
            maxLength={80}
            aria-label="키워드 추가"
            className="min-w-0 flex-1 rounded-lg border border-surface-border px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <Button type="submit" loading={addMutation.isPending} disabled={input.trim().length < 2}>
            추가
          </Button>
        </form>
        {error && <p className="mt-2 text-xs text-red-600 dark:text-red-300">{error}</p>}

        <div className="mt-4">
          {watchesLoading ? (
            <div className="h-7 w-44 animate-pulse rounded-full bg-surface-muted" />
          ) : hasKeywords ? (
            <div className="flex flex-wrap gap-2">
              {watches!.map((w) => (
                <Badge
                  key={w.id}
                  color="indigo"
                  className="gap-1.5 rounded-full py-1 pl-3 pr-1.5 text-sm"
                >
                  {w.keyword}
                  <button
                    onClick={() => removeMutation.mutate(w.id)}
                    aria-label={`${w.keyword} 키워드 삭제`}
                    className="flex h-5 w-5 items-center justify-center rounded-full text-primary-500 transition-colors hover:bg-primary-200/60 hover:text-primary-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500"
                  >
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path strokeLinecap="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                  </button>
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-ink-400">
              아직 등록한 키워드가 없습니다. 위 입력창에 추가해 보세요.
            </p>
          )}
        </div>
      </div>

      {/* 진행 추가 토스트 */}
      {addedTitle && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-green-200 dark:border-green-500/30 bg-green-50 dark:bg-green-500/15 px-3 py-2 text-sm text-green-800 dark:text-green-300">
          <span>✓ &lsquo;{addedTitle}&rsquo; 을(를) 진행 관리에 추가했어요.</span>
          <a href="/pipeline" className="ml-auto font-medium underline">
            진행 관리 보기 →
          </a>
        </div>
      )}

      {/* 매칭 공고 피드 */}
      {hasKeywords && (
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink-700">매칭 공고</h2>
          {matchCount > 0 && (
            <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-primary-100 dark:bg-primary-500/20 px-1.5 text-xs font-bold text-primary-700 dark:text-primary-300">
              {matchCount}
            </span>
          )}
        </div>
      )}

      {!hasKeywords ? (
        <EmptyState
          title="키워드를 추가해 보세요"
          description="등록한 키워드가 제목·기관·내용에 들어간 열린 공고를 AI 추천과 별개로 모아드려요. 도메인 키워드(예: 수처리·막여과·데이터 구축)를 넣어보세요."
          icon={watchIcon}
        />
      ) : matchesLoading ? (
        <SkeletonRows />
      ) : isError ? (
        <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/15 px-5 py-4 text-sm text-red-700 dark:text-red-300">
          매칭 공고를 불러오는 중 오류가 발생했습니다.
        </div>
      ) : matchCount === 0 ? (
        <EmptyState
          title="매칭되는 공고가 아직 없어요"
          description="등록한 키워드가 제목·기관·내용에 들어간 열린 공고가 아직 없습니다. 새 공고가 수집되면 여기에 표시됩니다."
          icon={watchIcon}
        />
      ) : (
        <RecommendationList items={matches!} onAddToPipeline={handleAddToPipeline} />
      )}
    </div>
  );
}
