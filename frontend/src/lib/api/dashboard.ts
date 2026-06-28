import { apiFetch } from "./client";
import type { StatsOut, CollectionStats } from "@/types/api";
import { MOCK_STATS } from "@/lib/mock/mockData";

export async function getDashboardStats(mock = false): Promise<StatsOut> {
  if (mock) return MOCK_STATS;
  return apiFetch<StatsOut>("/dashboard/stats");
}

/** 데이터 수집 현황 — 요약·기간별 추세·소스/분야/예산/낙찰 분석(실데이터 전용). */
export async function getCollectionStats(): Promise<CollectionStats> {
  return apiFetch<CollectionStats>("/dashboard/collection");
}
