import { apiFetch } from "./client";
import type { RecommendationItem } from "@/types/api";

export interface ReminderItem {
  tracked_via: "saved" | "pursuit";
  opportunity: RecommendationItem;
}

/** 관심/진행 공고 중 마감 임박분(회사 설정 윈도우, 기본 D-3), 임박순. */
export function getReminders(): Promise<ReminderItem[]> {
  return apiFetch<ReminderItem[]>("/reminders");
}
