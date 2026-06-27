import { apiFetch } from "./client";
import type { RecommendationItem } from "@/types/api";

export interface KeywordWatch {
  id: string;
  keyword: string;
  created_at: string;
}

/** 등록한 키워드 목록(오래된순). */
export function getWatches(): Promise<KeywordWatch[]> {
  return apiFetch<KeywordWatch[]>("/watches");
}

/** 키워드 추가(2~80자, 대소문자 무시 중복은 서버에서 멱등). */
export function addWatch(keyword: string): Promise<KeywordWatch> {
  return apiFetch<KeywordWatch>("/watches", {
    method: "POST",
    body: JSON.stringify({ keyword }),
  });
}

export function removeWatch(id: string): Promise<unknown> {
  return apiFetch(`/watches/${id}`, { method: "DELETE" });
}

/** 키워드(제목 포함) 매칭 공고 피드. */
export function getWatchMatches(): Promise<RecommendationItem[]> {
  return apiFetch<RecommendationItem[]>("/watches/matches");
}
