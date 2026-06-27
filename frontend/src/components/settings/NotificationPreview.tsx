"use client";

import { useQuery } from "@tanstack/react-query";
import { getBriefingPreview } from "@/lib/api/settings";

const SOURCE_LABEL: Record<string, string> = {
  narajangter: "나라장터",
  kstartup: "K-스타트업",
  ntis: "NTIS",
  bizinfo: "기업마당",
};

const KAKAO_YELLOW = "#FEE500";
const KAKAO_BROWN = "#3C1E1E";
const KAKAO_CHAT_BG = "#B2C7DA";

export function NotificationPreview() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["notification", "preview"],
    queryFn: getBriefingPreview,
  });

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-base font-semibold text-gray-900">알림 미리보기</h2>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-xs font-medium text-primary-600 hover:underline disabled:opacity-50"
        >
          {isFetching ? "불러오는 중…" : "새로고침"}
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-3">
        매일 {data?.send_hour ?? 8}:00 KST에 발송될 카카오 알림톡 내용입니다 (실제 추천 기반).
      </p>

      {/* 적용 중인 맞춤 알림 규칙(#4) */}
      {data && (data.min_score != null || (data.excluded_sources?.length ?? 0) > 0) && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-gray-400">적용 규칙</span>
          {data.min_score != null && (
            <span className="rounded-full bg-primary-50 px-2 py-0.5 font-medium text-primary-700 ring-1 ring-inset ring-primary-600/10">
              적합도 {data.min_score}점 이상
            </span>
          )}
          {(data.excluded_sources ?? []).map((s) => (
            <span key={s} className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-500">
              {SOURCE_LABEL[s] ?? s} 제외
            </span>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-lg bg-gray-100" />
      ) : isError ? (
        <p className="py-8 text-center text-sm text-red-600">
          미리보기를 불러오지 못했습니다.{" "}
          <button onClick={() => refetch()} className="font-medium underline">
            다시 시도
          </button>
        </p>
      ) : !data || data.count === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          오늘 발송할 추천 공고가 없습니다.
        </p>
      ) : (
        <>
          {/* KakaoTalk 채팅 스타일 미리보기 */}
          <div className="rounded-xl p-4" style={{ backgroundColor: KAKAO_CHAT_BG }}>
            <div className="mx-auto max-w-sm">
              <div className="mb-1.5 flex items-center gap-2">
                <div
                  className="flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold"
                  style={{ backgroundColor: KAKAO_YELLOW, color: KAKAO_BROWN }}
                >
                  B
                </div>
                <span className="text-xs font-medium text-gray-700">WaterNature 알림</span>
              </div>

              <div className="overflow-hidden rounded-2xl rounded-tl-md bg-white shadow-sm">
                <div
                  className="px-4 py-2 text-xs font-semibold"
                  style={{ backgroundColor: KAKAO_YELLOW, color: KAKAO_BROWN }}
                >
                  알림톡 도착
                </div>
                <div className="px-4 py-3">
                  <p className="mb-2.5 text-sm font-semibold leading-snug text-gray-900">
                    [WaterNature] {data.company_name}님,
                    <br />
                    오늘의 맞춤 공고 {data.count}건이 도착했어요 📡
                  </p>

                  <div className="space-y-2">
                    {data.items.map((it, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-gray-100 bg-gray-50 p-2.5"
                      >
                        <p className="text-[13px] font-medium leading-snug text-gray-900">
                          {i + 1}. {it.title}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-gray-500">
                          {it.score != null ? (
                            <span className="font-semibold text-primary-600">
                              적합도 {Math.round(it.score)}
                            </span>
                          ) : it.matched_keywords && it.matched_keywords.length > 0 ? (
                            <span className="inline-flex items-center gap-0.5 font-semibold text-primary-600">
                              <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <circle cx="11" cy="11" r="7" />
                                <path strokeLinecap="round" d="m21 21-4.3-4.3" />
                              </svg>
                              {it.matched_keywords.join(", ")}
                            </span>
                          ) : null}
                          {it.agency && (
                            <>
                              <span>·</span>
                              <span>{it.agency}</span>
                            </>
                          )}
                          {it.budget && it.budget !== "-" && (
                            <>
                              <span>·</span>
                              <span>{it.budget}</span>
                            </>
                          )}
                          {it.dday && it.dday !== "-" && (
                            <>
                              <span>·</span>
                              <span className="text-red-500">{it.dday}</span>
                            </>
                          )}
                          <span className="ml-auto rounded border border-surface-border bg-surface-card px-1.5 py-0.5 text-[10px] text-gray-400">
                            {SOURCE_LABEL[it.source] ?? it.source}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-3 rounded-lg bg-gray-100 py-2 text-center text-[13px] font-medium text-gray-700">
                    오늘의 추천 전체 보기 →
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 발송 진단 */}
          <div className="mt-4">
            {data.would_send ? (
              <p className="text-sm text-green-700">
                ✓ 발송 준비 완료 — 매일 {data.send_hour}:00 KST에 카카오 알림톡으로 발송됩니다.
              </p>
            ) : (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
                <p className="mb-1 text-sm font-medium text-amber-800">
                  발송 대기 — 아래 조건이 충족되면 자동 발송됩니다
                </p>
                <ul className="list-inside list-disc space-y-0.5 text-xs text-amber-700">
                  {data.blockers.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
