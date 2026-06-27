import { apiFetch } from "./client";

export interface FunnelMetrics {
  total_companies: number;
  ready_companies: number;
  paying_companies: number;
  paying_target: number;
  mrr: number;
  mrr_target: number;
  recommended: number;
  opened: number;
  saved: number;
  participated: number;
  rates: { open: number; save: number; participate: number };
  targets: { open: number; save: number; participate: number };
}

/** 플랫폼 집계 North Star 지표 (운영자 전용 — 비-운영자는 403). */
export function getFunnelMetrics(): Promise<FunnelMetrics> {
  return apiFetch<FunnelMetrics>("/metrics/funnel");
}
