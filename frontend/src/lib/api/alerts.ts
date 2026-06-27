import { apiFetch } from "./client";
import type { RecommendationItem } from "@/types/api";
import type { ReminderItem } from "./reminders";

export interface AlertsData {
  deadline_reminders: ReminderItem[];
  keyword_hits: RecommendationItem[];
}

/** 인앱 알림 — 마감 임박(관심/진행) + 최근 키워드 매칭 새 공고. */
export function getAlerts(): Promise<AlertsData> {
  return apiFetch<AlertsData>("/alerts");
}
