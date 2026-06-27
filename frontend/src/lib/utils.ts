// ────────────────────────────────────────────────────────────────────────────
// Utility helpers
// ────────────────────────────────────────────────────────────────────────────

import type { RecommendationItem, SortKey } from "@/types/api";

/**
 * Format budget in Korean units: 억원 / 만원 / 원
 */
export function formatBudget(amount: number | null | undefined): string {
  if (amount == null) return "금액미정";
  if (amount >= 100_000_000) {
    const uk = amount / 100_000_000;
    return `${uk % 1 === 0 ? uk.toFixed(0) : uk.toFixed(1)}억원`;
  }
  if (amount >= 10_000) {
    const man = amount / 10_000;
    return `${man % 1 === 0 ? man.toFixed(0) : man.toFixed(0)}만원`;
  }
  return `${amount.toLocaleString("ko-KR")}원`;
}

/**
 * Return urgency level for D-day
 */
export function getDDayUrgency(dDay: number | null | undefined): "critical" | "warning" | "normal" {
  if (dDay == null) return "normal"; // 마감일 미정 → 중립(옅음)
  if (dDay <= 3) return "critical"; // D-3 이내(+마감 경과) = 빨강(임박만)
  if (dDay <= 10) return "warning"; // 임박 = 앰버
  return "normal"; // 여유 = 회색
}

/**
 * Format D-day as "D-3", "D-0", "D+1", "마감"
 */
export function formatDDay(dDay: number | null | undefined): string {
  if (dDay == null) return "마감일 미정";
  if (dDay < 0) return "마감";
  if (dDay === 0) return "D-DAY";
  return `D-${dDay}`;
}

/**
 * Format score as percentage label
 */
export function formatScore(score: number | null | undefined): string {
  if (score == null) return "-";
  return `${score}%`;
}

/**
 * Format ISO date string to Korean short format
 */
export function formatDeadline(deadline: string | null | undefined): string {
  if (!deadline) return "마감일 미정";
  const d = new Date(deadline);
  return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

/**
 * Clamp class utility
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Return the URL only if it is a safe absolute http(s) URL, otherwise undefined.
 *
 * `detail_url` originates from external, non-trusted data (scraped 나라장터/
 * K-Startup/NTIS records + LLM pipeline). Rendering it straight into an <a href>
 * or window.open allows `javascript:`/`data:`-scheme injection (XSS) and silent
 * open-redirect. Guard every such sink with this helper.
 */
export function safeHttpUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url); // absolute URLs only — rejects relative/`javascript:`/`data:`
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Recommendation sorting (client-side — used by the dashboard top-N list)
// ────────────────────────────────────────────────────────────────────────────

const FEASIBILITY_RANK: Record<string, number> = {
  go: 0,
  review: 1,
  no_go: 2,
};

/** Rank of a feasibility verdict; missing/unknown verdicts sort last. */
function feasibilityRank(item: RecommendationItem): number {
  const verdict = item.feasibility?.verdict;
  if (verdict && verdict in FEASIBILITY_RANK) return FEASIBILITY_RANK[verdict];
  return 3;
}

/**
 * Compare two nullable numbers so that nulls always sort to the end,
 * with non-null values ordered by `dir` ("asc" | "desc").
 */
function compareNullableNumber(
  a: number | null | undefined,
  b: number | null | undefined,
  dir: "asc" | "desc"
): number {
  const aNull = a == null;
  const bNull = b == null;
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  return dir === "asc" ? a - b : b - a;
}

/** Epoch millis for an ISO date string, or null when absent/invalid. */
function toTime(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : t;
}

/**
 * Return a new array of recommendations ordered by the given sort key.
 * Stable, non-mutating; nulls always sort to the end.
 *   score        → score desc
 *   deadline     → d_day asc (soonest first; falls back to deadline date)
 *   posted       → posted_at desc (newest first)
 *   budget       → budget_amount desc
 *   feasibility  → verdict go<review<no_go<none, tie-broken by score desc
 */
export function sortRecommendations<T extends RecommendationItem>(
  items: T[],
  sort: SortKey
): T[] {
  const sorted = [...items];
  switch (sort) {
    case "deadline":
      sorted.sort((a, b) => {
        const byDay = compareNullableNumber(a.d_day, b.d_day, "asc");
        if (byDay !== 0) return byDay;
        return compareNullableNumber(toTime(a.deadline), toTime(b.deadline), "asc");
      });
      break;
    case "posted":
      sorted.sort((a, b) =>
        compareNullableNumber(toTime(a.posted_at), toTime(b.posted_at), "desc")
      );
      break;
    case "budget":
      sorted.sort((a, b) =>
        compareNullableNumber(a.budget_amount, b.budget_amount, "desc")
      );
      break;
    case "feasibility":
      sorted.sort((a, b) => {
        const byRank = feasibilityRank(a) - feasibilityRank(b);
        if (byRank !== 0) return byRank;
        return compareNullableNumber(a.score, b.score, "desc");
      });
      break;
    case "score":
    default:
      sorted.sort((a, b) => compareNullableNumber(a.score, b.score, "desc"));
      break;
  }
  return sorted;
}
