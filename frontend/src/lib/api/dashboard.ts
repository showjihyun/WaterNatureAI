import { apiFetch } from "./client";
import type { StatsOut } from "@/types/api";
import { MOCK_STATS } from "@/lib/mock/mockData";

export async function getDashboardStats(mock = false): Promise<StatsOut> {
  if (mock) return MOCK_STATS;
  return apiFetch<StatsOut>("/dashboard/stats");
}
