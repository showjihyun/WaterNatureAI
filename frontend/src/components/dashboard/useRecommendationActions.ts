"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { RecommendationItem } from "@/types/api";
import { recordAction, unsaveOpportunity } from "@/lib/api/opportunities";
import { safeHttpUrl } from "@/lib/utils";

/**
 * Shared save / open behaviour for a single recommendation, used by both the
 * card and the list-row presentations so they keep identical logic:
 * recordAction / unsaveOpportunity, React Query invalidation of
 * ["dashboard","stats"] and ["recommendations","today"], and the mock branch.
 */
export function useRecommendationActions(item: RecommendationItem, mock: boolean) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(item.saved);
  const [savingInProgress, setSavingInProgress] = useState(false);

  async function handleSaveToggle() {
    if (savingInProgress) return;
    setSavingInProgress(true);
    try {
      if (saved) {
        await unsaveOpportunity(item.opportunity_id, mock);
        setSaved(false);
      } else {
        await recordAction(item.opportunity_id, "saved", mock);
        setSaved(true);
      }
      if (!mock) {
        queryClient.invalidateQueries({ queryKey: ["dashboard", "stats"] });
        queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
        queryClient.invalidateQueries({ queryKey: ["recommendations", "saved"] });
        // 관심 추가/해제 → 마감 임박(대시보드) 갱신
        queryClient.invalidateQueries({ queryKey: ["reminders"] });
      }
    } finally {
      setSavingInProgress(false);
    }
  }

  async function handleViewSource() {
    if (!mock) {
      try {
        await recordAction(item.opportunity_id, "opened", false);
        queryClient.invalidateQueries({ queryKey: ["dashboard", "stats"] });
      } catch {
        // fire-and-forget
      }
    }
    const safe = safeHttpUrl(item.detail_url);
    if (safe) {
      window.open(safe, "_blank", "noopener,noreferrer");
    }
  }

  return { saved, savingInProgress, handleSaveToggle, handleViewSource };
}
