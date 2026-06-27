import { apiFetch } from "./client";
import type { RecommendationItem } from "@/types/api";
import { MOCK_RECOMMENDATIONS } from "@/lib/mock/mockData";

export async function getTodayRecommendations(
  mock = false
): Promise<RecommendationItem[]> {
  if (mock) return MOCK_RECOMMENDATIONS;
  return apiFetch<RecommendationItem[]>("/recommendations/today");
}

/** 관심 등록(♥)한 공고 목록 (최근 저장순). */
export async function getSavedOpportunities(): Promise<RecommendationItem[]> {
  return apiFetch<RecommendationItem[]>("/saved");
}
