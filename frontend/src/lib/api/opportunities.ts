import { apiFetch } from "./client";
import type {
  OpportunityList,
  OpportunityDetail,
  OpportunityFilters,
  ActionType,
  AwardList,
} from "@/types/api";
import {
  MOCK_OPPORTUNITY_LIST,
  MOCK_RECOMMENDATIONS,
} from "@/lib/mock/mockData";
import { sortRecommendations } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";

export async function listOpportunities(
  filters: OpportunityFilters = {},
  mock = false
): Promise<OpportunityList> {
  if (mock) {
    // Mock has no server; apply source filter + sort client-side so the controls work.
    let items = MOCK_OPPORTUNITY_LIST.items;
    if (filters.sources?.length) {
      // 목 데이터는 출처를 한글 라벨로 보관 → 코드/라벨 둘 다로 매칭.
      const wanted = new Set(filters.sources.flatMap((c) => [c, sourceLabel(c)]));
      items = items.filter((i) => i.source != null && wanted.has(i.source));
    }
    return {
      ...MOCK_OPPORTUNITY_LIST,
      items: sortRecommendations(items, filters.sort ?? "score"),
      total: items.length,
    };
  }
  const params = new URLSearchParams();
  if (filters.agency) params.set("agency", filters.agency);
  filters.sources?.forEach((s) => params.append("source", s));
  if (filters.region) params.set("region", filters.region);
  if (filters.category) params.set("category", filters.category);
  if (filters.industry) params.set("industry", filters.industry);
  if (filters.budget_min != null)
    params.set("budget_min", String(filters.budget_min));
  if (filters.budget_max != null)
    params.set("budget_max", String(filters.budget_max));
  if (filters.deadline_before)
    params.set("deadline_before", filters.deadline_before);
  if (filters.min_score != null)
    params.set("min_score", String(filters.min_score));
  if (filters.feasibility) params.set("feasibility", filters.feasibility);
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.size) params.set("size", String(filters.size));
  const qs = params.toString();
  return apiFetch<OpportunityList>(`/opportunities${qs ? `?${qs}` : ""}`);
}

export async function getOpportunityDetail(
  id: string,
  mock = false
): Promise<OpportunityDetail> {
  if (mock) {
    const opp = MOCK_RECOMMENDATIONS.find((r) => r.opportunity_id === id);
    return {
      opportunity: {
        id: opp?.opportunity_id ?? id,
        title: opp?.title ?? "알 수 없는 공고",
        agency: opp?.agency ?? null,
        category: opp?.category ?? null,
        budget_amount: opp?.budget_amount ?? null,
        deadline: opp?.deadline ?? null,
        detail_url: opp?.detail_url ?? null,
        source: opp?.source ?? "나라장터",
        status: "open",
      },
      match: opp
        ? { score: opp.score, reasons: opp.reasons, subscore: null, risk: null }
        : null,
      other_sources: opp?.other_sources ?? [],
    };
  }
  return apiFetch<OpportunityDetail>(`/opportunities/${id}`);
}

export async function recordAction(
  opportunityId: string,
  type: ActionType,
  mock = false
): Promise<void> {
  if (mock) return;
  await apiFetch(`/opportunities/${opportunityId}/actions`, {
    method: "POST",
    body: JSON.stringify({ type }),
  });
}

export async function unsaveOpportunity(
  opportunityId: string,
  mock = false
): Promise<void> {
  if (mock) return;
  await apiFetch(`/opportunities/${opportunityId}/actions/saved`, {
    method: "DELETE",
  });
}

/** '관심없음' — 추천에서 제외(+사유). */
export async function hideOpportunity(
  opportunityId: string,
  reason?: string,
  mock = false
): Promise<void> {
  if (mock) return;
  await apiFetch(`/opportunities/${opportunityId}/hide`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

/** '관심없음' 취소(실행취소). */
export async function unhideOpportunity(
  opportunityId: string,
  mock = false
): Promise<void> {
  if (mock) return;
  await apiFetch(`/opportunities/${opportunityId}/hide`, { method: "DELETE" });
}

/** 낙찰(결과) 목록 — 기관/공고명 검색·분야·페이지네이션. */
export async function listAwards(
  params: { q?: string; category?: string; page?: number; size?: number } = {},
  mock = false
): Promise<AwardList> {
  if (mock) return { items: [], total: 0, page: 1, size: 20 };
  const p = new URLSearchParams();
  if (params.q) p.set("q", params.q);
  if (params.category) p.set("category", params.category);
  if (params.page) p.set("page", String(params.page));
  if (params.size) p.set("size", String(params.size));
  const qs = p.toString();
  return apiFetch<AwardList>(`/opportunities/awards${qs ? `?${qs}` : ""}`);
}
