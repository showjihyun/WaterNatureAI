"use client";

import { useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import type { OpportunityFilters } from "@/types/api";

// ── helpers ──────────────────────────────────────────────────────────────────

/** Add `days` calendar days to today and return an ISO datetime string (UTC). */
function deadlineInDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(23, 59, 59, 999);
  return d.toISOString();
}

// ── preset definitions ────────────────────────────────────────────────────────

type BudgetPreset = "all" | "lt1" | "1to5" | "gt5";
type DeadlinePreset = "all" | "7d" | "14d" | "30d";
type ScorePreset = "all" | "40" | "50" | "60";
type FeasibilityPreset = "all" | "go" | "review" | "no_go";

interface BudgetOption { value: BudgetPreset; label: string; min?: number; max?: number }
interface DeadlineOption { value: DeadlinePreset; label: string; days?: number }
interface ScoreOption { value: ScorePreset; label: string; min?: number }
interface FeasibilityOption { value: FeasibilityPreset; label: string; icon?: string }

const BUDGET_OPTIONS: BudgetOption[] = [
  { value: "all", label: "전체" },
  { value: "lt1", label: "~1억", max: 100_000_000 },
  { value: "1to5", label: "1~5억", min: 100_000_000, max: 500_000_000 },
  { value: "gt5", label: "5억+", min: 500_000_000 },
];

const DEADLINE_OPTIONS: DeadlineOption[] = [
  { value: "all", label: "전체" },
  { value: "7d", label: "1주 이내", days: 7 },
  { value: "14d", label: "2주 이내", days: 14 },
  { value: "30d", label: "1개월 이내", days: 30 },
];

const SCORE_OPTIONS: ScoreOption[] = [
  { value: "all", label: "전체" },
  { value: "40", label: "40+", min: 40 },
  { value: "50", label: "50+", min: 50 },
  { value: "60", label: "60+", min: 60 },
];

const FEASIBILITY_OPTIONS: FeasibilityOption[] = [
  { value: "all", label: "전체" },
  { value: "go", label: "수행가능", icon: "🟢" },
  { value: "review", label: "검토", icon: "🟡" },
  { value: "no_go", label: "어려움", icon: "🔴" },
];

// 출처 — 공고가 들어오는 공공 사이트(다중선택). 빈 선택 = 전체. 라벨은 sourceLabel().
const SOURCE_OPTIONS: string[] = ["narajangter", "kstartup", "ntis", "bizinfo"];

// ── derived state from filter values ─────────────────────────────────────────

function detectBudgetPreset(filters: OpportunityFilters): BudgetPreset {
  const { budget_min, budget_max } = filters;
  if (budget_min == null && budget_max == null) return "all";
  if (budget_max === 100_000_000 && budget_min == null) return "lt1";
  if (budget_min === 100_000_000 && budget_max === 500_000_000) return "1to5";
  if (budget_min === 500_000_000 && budget_max == null) return "gt5";
  return "all";
}

function detectDeadlinePreset(filters: OpportunityFilters): DeadlinePreset {
  if (!filters.deadline_before) return "all";
  // Match by reconstructing — if the stored date is within ±1 min of one of our presets,
  // treat it as that preset. Otherwise show "all" (user set externally).
  const stored = new Date(filters.deadline_before).getTime();
  for (const opt of DEADLINE_OPTIONS) {
    if (opt.days == null) continue;
    const candidate = new Date(deadlineInDays(opt.days)).getTime();
    if (Math.abs(stored - candidate) < 60_000 * 60) return opt.value; // within 1h tolerance
  }
  return "all";
}

function detectScorePreset(filters: OpportunityFilters): ScorePreset {
  if (filters.min_score == null) return "all";
  const hit = SCORE_OPTIONS.find((o) => o.min === filters.min_score);
  return hit ? hit.value : "all";
}

function detectFeasibilityPreset(filters: OpportunityFilters): FeasibilityPreset {
  if (!filters.feasibility) return "all";
  return filters.feasibility as FeasibilityPreset;
}

// ── chip primitive ────────────────────────────────────────────────────────────

interface ChipProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}

function Chip({ active, onClick, children, className }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
        active
          ? "bg-primary-600 text-white shadow-sm"
          : "bg-surface border border-surface-border text-ink-600 hover:bg-primary-50 hover:text-primary-700 hover:border-primary-300",
        className
      )}
    >
      {children}
    </button>
  );
}

// ── group label ───────────────────────────────────────────────────────────────

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 text-xs font-semibold text-ink-400 uppercase tracking-wide">
      {children}
    </span>
  );
}

// ── main component ─────────────────────────────────────────────────────────────

export interface OpportunityFilterBarProps {
  filters: OpportunityFilters;
  onChange: (patch: Partial<OpportunityFilters>) => void;
  onReset: () => void;
  /** Number of active filter dimensions (excluding sort/page/size). */
  activeCount: number;
}

export function OpportunityFilterBar({
  filters,
  onChange,
  onReset,
  activeCount,
}: OpportunityFilterBarProps) {
  // ── agency debounce ────────────────────────────────────────────────────────
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleAgencyInput = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onChange({ agency: value.trim() || undefined, page: 1 });
      }, 400);
    },
    [onChange]
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // ── derived preset values ──────────────────────────────────────────────────
  const budgetPreset = detectBudgetPreset(filters);
  const deadlinePreset = detectDeadlinePreset(filters);
  const scorePreset = detectScorePreset(filters);
  const feasibilityPreset = detectFeasibilityPreset(filters);
  const selectedSources = filters.sources ?? [];

  // ── handlers ───────────────────────────────────────────────────────────────

  function toggleSource(code: string) {
    const next = selectedSources.includes(code)
      ? selectedSources.filter((c) => c !== code)
      : [...selectedSources, code];
    onChange({ sources: next.length ? next : undefined, page: 1 });
  }

  function applyBudget(opt: BudgetOption) {
    onChange({
      budget_min: opt.min,
      budget_max: opt.max,
      page: 1,
    });
  }

  function applyDeadline(opt: DeadlineOption) {
    onChange({
      deadline_before: opt.days != null ? deadlineInDays(opt.days) : undefined,
      page: 1,
    });
  }

  function applyScore(opt: ScoreOption) {
    onChange({ min_score: opt.min, page: 1 });
  }

  function applyFeasibility(opt: FeasibilityOption) {
    onChange({
      feasibility: opt.value === "all" ? undefined : (opt.value as "go" | "review" | "no_go"),
      page: 1,
    });
  }

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div
      role="search"
      aria-label="공고 필터"
      className="rounded-xl border border-surface-border bg-surface-card shadow-sm"
    >
      {/* Filter row — wraps to multiple lines (no horizontal scroll) */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 px-4 py-3">

          {/* Agency search */}
          <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto">
            <GroupLabel>기관</GroupLabel>
            <div className="relative flex-1 sm:flex-none">
              <label htmlFor="filter-agency" className="sr-only">기관명 검색</label>
              <input
                id="filter-agency"
                type="text"
                defaultValue={filters.agency ?? ""}
                key={filters.agency ?? "agency-reset"}
                onChange={(e) => handleAgencyInput(e.target.value)}
                placeholder="기관명 검색"
                className={cn(
                  "h-7 w-full rounded-lg border px-2.5 text-xs text-ink sm:w-36",
                  "placeholder:text-ink-400 bg-surface",
                  "focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
                  filters.agency
                    ? "border-primary-400 ring-1 ring-primary-200"
                    : "border-surface-border"
                )}
              />
            </div>
          </div>
          {/* Source presets (출처 — 다중선택) */}
          <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto">
            <GroupLabel>출처</GroupLabel>
            <div className="flex flex-wrap gap-1">
              <Chip
                active={selectedSources.length === 0}
                onClick={() => onChange({ sources: undefined, page: 1 })}
              >
                전체
              </Chip>
              {SOURCE_OPTIONS.map((code) => (
                <Chip
                  key={code}
                  active={selectedSources.includes(code)}
                  onClick={() => toggleSource(code)}
                >
                  {sourceLabel(code)}
                </Chip>
              ))}
            </div>
          </div>
          {/* Budget presets */}
          <div className="flex shrink-0 items-center gap-2">
            <GroupLabel>예산</GroupLabel>
            <div className="flex flex-wrap gap-1">
              {BUDGET_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={budgetPreset === opt.value}
                  onClick={() => applyBudget(opt)}
                >
                  {opt.label}
                </Chip>
              ))}
            </div>
          </div>
          {/* Deadline presets */}
          <div className="flex shrink-0 items-center gap-2">
            <GroupLabel>마감</GroupLabel>
            <div className="flex flex-wrap gap-1">
              {DEADLINE_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={deadlinePreset === opt.value}
                  onClick={() => applyDeadline(opt)}
                >
                  {opt.label}
                </Chip>
              ))}
            </div>
          </div>
          {/* Score presets */}
          <div className="flex shrink-0 items-center gap-2">
            <GroupLabel>적합도</GroupLabel>
            <div className="flex flex-wrap gap-1">
              {SCORE_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={scorePreset === opt.value}
                  onClick={() => applyScore(opt)}
                >
                  {opt.label}
                </Chip>
              ))}
            </div>
          </div>
          {/* Feasibility presets */}
          <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto">
            <GroupLabel>수행가능성</GroupLabel>
            <div className="flex flex-wrap gap-1">
              {FEASIBILITY_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={feasibilityPreset === opt.value}
                  onClick={() => applyFeasibility(opt)}
                >
                  {opt.icon && <span className="mr-1">{opt.icon}</span>}
                  {opt.label}
                </Chip>
              ))}
            </div>
          </div>
          {/* Reset */}
          <button
            type="button"
            onClick={onReset}
            className={cn(
              "shrink-0 inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
              activeCount > 0
                ? "text-primary-600 hover:bg-primary-50"
                : "text-ink-400 hover:bg-gray-100"
            )}
            aria-label="필터 초기화"
          >
            <svg
              className="h-3 w-3"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
            초기화
            {activeCount > 0 && (
              <span className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary-600 text-[10px] font-bold text-white">
                {activeCount}
              </span>
            )}
          </button>
      </div>
    </div>
  );
}

// ── active filter counter (exported helper) ───────────────────────────────────

/**
 * Count how many filter dimensions are active (agency, budget, deadline,
 * min_score, feasibility). Excludes sort / page / size.
 */
export function countActiveFilters(filters: OpportunityFilters): number {
  let n = 0;
  if (filters.agency) n++;
  if (filters.budget_min != null || filters.budget_max != null) n++;
  if (filters.deadline_before) n++;
  if (filters.min_score != null) n++;
  if (filters.feasibility) n++;
  if (filters.sources && filters.sources.length) n++;
  return n;
}
