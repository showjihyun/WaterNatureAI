import { apiFetch } from "./client";
import type { RecommendationItem } from "@/types/api";

export type PursuitStage = "reviewing" | "preparing" | "submitted" | "done";

export interface PursuitItem {
  stage: PursuitStage;
  note: string | null;
  opportunity: RecommendationItem;
}

/** 단계 정의(순서). */
export const PURSUIT_STAGES: { key: PursuitStage; label: string }[] = [
  { key: "reviewing", label: "검토중" },
  { key: "preparing", label: "준비중" },
  { key: "submitted", label: "제출" },
  { key: "done", label: "완료" },
];

export function getPursuits(): Promise<PursuitItem[]> {
  return apiFetch<PursuitItem[]>("/pursuits");
}

export function addPursuit(opportunityId: string, stage?: PursuitStage): Promise<unknown> {
  return apiFetch("/pursuits", {
    method: "POST",
    body: JSON.stringify({ opportunity_id: opportunityId, stage }),
  });
}

export function updatePursuitStage(
  opportunityId: string,
  stage: PursuitStage
): Promise<unknown> {
  return apiFetch(`/pursuits/${opportunityId}`, {
    method: "PATCH",
    body: JSON.stringify({ stage }),
  });
}

export function removePursuit(opportunityId: string): Promise<unknown> {
  return apiFetch(`/pursuits/${opportunityId}`, { method: "DELETE" });
}
