"use client";

import { Suspense, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { ScoreBadge } from "@/components/dashboard/ScoreBadge";
import { DaysBadge } from "@/components/dashboard/DaysBadge";
import { FeasibilityBadge } from "@/components/dashboard/FeasibilityBadge";
import { LoadingPage } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { getOpportunityDetail, recordAction } from "@/lib/api/opportunities";
import { formatBudget, safeHttpUrl } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import { InfoPopover } from "@/components/ui/InfoPopover";

function OpportunityDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const isMock = searchParams.get("mock") === "1";
  const id = params.id as string;

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["opportunity", id, isMock],
    queryFn: () => getOpportunityDetail(id, isMock),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <LoadingPage />;
  if (error || !data) {
    return (
      <AppShell>
        <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/15 px-5 py-4 text-sm text-red-700 dark:text-red-300">
          공고를 불러오지 못했습니다.{" "}
          <Link href="/opportunities" className="underline">
            목록으로
          </Link>
        </div>
      </AppShell>
    );
  }

  const { opportunity, match, other_sources, feasibility } = data;

  function handleView() {
    if (!isMock) {
      recordAction(id, "opened", false).catch(console.error);
    }
    const safe = safeHttpUrl(opportunity.detail_url);
    if (safe) {
      window.open(safe, "_blank", "noopener,noreferrer");
    }
  }

  async function handleSave() {
    if (isMock || saving || saved) return;
    setSaving(true);
    try {
      await recordAction(id, "saved", false);
      setSaved(true);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  }

  const dDay = opportunity.deadline
    ? Math.ceil(
        (new Date(opportunity.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
      )
    : null;

  // 설명이 제목 재탕(스텁)이 아니라 실제 본문일 때만 텍스트로 노출 — 아니면 원문 안내.
  const desc = opportunity.description?.trim() ?? "";
  const hasRichDescription = desc.length > opportunity.title.length + 25;

  return (
    <AppShell>
      {/* Breadcrumb */}
      <div className="mb-5 flex items-center gap-2 text-sm text-ink-400">
        <Link href="/opportunities" className="hover:text-ink-600">
          공고 탐색
        </Link>
        <span>/</span>
        <span className="text-ink-600 truncate max-w-xs">{opportunity.title}</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main */}
        <div className="lg:col-span-2 space-y-4">
          {/* Title card */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {opportunity.agency && (
                <Badge color="indigo">{opportunity.agency}</Badge>
              )}
              {opportunity.category && (
                <Badge color="gray">{opportunity.category}</Badge>
              )}
              {opportunity.source && (
                <Badge color="gray">출처: {sourceLabel(opportunity.source)}</Badge>
              )}
            </div>
            <h1 className="text-lg font-bold text-ink leading-snug mb-4">
              {opportunity.title}
            </h1>
            <div className="flex items-center justify-between flex-wrap gap-3">
              {match ? (
                <div className="flex items-center gap-1.5">
                  <InfoPopover title="적합도란?" ariaLabel="적합도 도움말">
                    <ul className="space-y-1.5 list-none">
                      <li>우리 회사 역량과 공고의 일치도를 0~100으로 점수화한 값이에요.</li>
                      <li>
                        <span className="font-medium text-ink-700">평가 항목:</span> 기술 적합(의미 유사도 + 키워드), 산업 적합, 지역 적합 등을 종합합니다.
                      </li>
                      <li>35점 이상인 공고만 추천에 노출돼요. 점수가 높을수록 우리 회사에 더 맞는 사업입니다.</li>
                    </ul>
                  </InfoPopover>
                  <ScoreBadge score={match.score} showBar />
                </div>
              ) : (
                <span className="text-xs text-ink-400">
                  내 회사 추천 목록 밖 공고예요 · 적합도 미산출
                </span>
              )}
              <DaysBadge dDay={dDay} deadline={opportunity.deadline} />
            </div>

            {/* Feasibility verdict */}
            {feasibility && (
              <div className="mt-4 pt-4 border-t border-surface-border">
                <div className="flex items-center gap-1.5 mb-2">
                  <p className="text-xs font-medium text-ink-400 uppercase tracking-wide">
                    수행 가능성
                  </p>
                  <InfoPopover title="수행 가능성이란?" ariaLabel="수행 가능성 도움말">
                    <ul className="space-y-1.5 list-none">
                      <li>설정한 &apos;수행 역량&apos;으로 이 사업을 실제로 감당할 수 있는지 판단해요.</li>
                      <li>🟢 수행 가능 · 🟡 검토 필요 · 🔴 수행 어려움</li>
                      <li>
                        <span className="font-medium text-ink-700">기준</span> — 수행 유형 일치 / 사업 규모(예산 vs 감당 가능 최대 규모) / 기술 수준.
                      </li>
                      <li>기준 값은 [설정 &gt; 수행 역량]에서 바꿀 수 있어요.</li>
                    </ul>
                  </InfoPopover>
                </div>
                <FeasibilityBadge feasibility={feasibility} compact={false} />
              </div>
            )}
          </div>

          {/* 공고 내용 */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-ink-600">공고 내용</h2>
            {hasRichDescription ? (
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-600">
                {opportunity.description}
              </p>
            ) : (
              <p className="text-sm text-ink-400">
                요약 정보만 제공돼요. 상세 공고문·자격요건·첨부파일은 원문에서 확인하세요.
              </p>
            )}
            <button
              onClick={handleView}
              disabled={!opportunity.detail_url}
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary-600 dark:text-primary-400 transition-colors hover:text-primary-700 dark:text-primary-300 disabled:opacity-40"
            >
              원문에서 전체 내용 보기
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </button>
          </div>

          {/* Match reasons */}
          {match && match.reasons.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-ink-700 mb-4 flex items-center gap-2">
                <svg className="h-4 w-4 text-primary-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                추천 근거
              </h2>
              <ul className="space-y-2">
                {match.reasons.map((reason, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <svg className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                    <span className="text-ink-700">{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk */}
          {match?.risk && (
            <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/15 p-5">
              <h2 className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-2 flex items-center gap-2">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
                주의사항
              </h2>
              <p className="text-sm text-amber-700 dark:text-amber-300">{match.risk}</p>
            </div>
          )}

          {/* Other sources */}
          {other_sources.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-ink-700 mb-3">타 공고 출처</h2>
              <div className="flex flex-wrap gap-2">
                {other_sources.map((src, i) => (
                  <Badge key={i} color="gray">
                    {sourceLabel(src)}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="rounded-xl border border-surface-border bg-surface-card p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-ink-700 mb-4">공고 정보</h2>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-ink-400 mb-0.5">예상 규모</dt>
                <dd className="font-semibold text-ink">{formatBudget(opportunity.budget_amount)}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-400 mb-0.5">마감일</dt>
                <dd className="font-medium text-ink">
                  {opportunity.deadline
                    ? new Date(opportunity.deadline).toLocaleDateString("ko-KR", {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                      })
                    : "미정"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-ink-400 mb-0.5">발주기관</dt>
                <dd className="font-medium text-ink">{opportunity.agency ?? "-"}</dd>
              </div>
              {opportunity.region && (
                <div>
                  <dt className="text-xs text-ink-400 mb-0.5">지역</dt>
                  <dd className="font-medium text-ink">{opportunity.region}</dd>
                </div>
              )}
              <div>
                <dt className="text-xs text-ink-400 mb-0.5">공고 상태</dt>
                <dd>
                  <span className="inline-flex items-center rounded-md bg-green-50 dark:bg-green-500/15 px-2 py-0.5 text-xs font-medium text-green-700 dark:text-green-300 ring-1 ring-inset ring-green-600/20">
                    {opportunity.status === "open" ? "진행 중" : opportunity.status}
                  </span>
                </dd>
              </div>
            </dl>

            <div className="mt-5 space-y-2">
              <Button
                onClick={handleView}
                disabled={!opportunity.detail_url}
                className="w-full"
              >
                원문 보기 →
              </Button>
              <Button
                variant="secondary"
                onClick={handleSave}
                loading={saving}
                disabled={isMock || saved}
                className="w-full"
              >
                {saved ? "관심 등록됨" : "관심 등록"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

export default function OpportunityDetailPage() {
  return (
    <Suspense fallback={<LoadingPage />}>
      <OpportunityDetailContent />
    </Suspense>
  );
}
