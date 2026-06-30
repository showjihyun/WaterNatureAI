"use client";

import { useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { sourceLabel } from "@/lib/sourceLabel";
import { KSIC_CHOICES } from "@/lib/ksic";
import { Chip } from "@/components/ui/Chip";
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

// 출처 — 운영 활성 수집기만(다중선택). 빈 선택 = 전체. 라벨은 sourceLabel().
// bizinfo(기업마당)는 수집기 비활성(데이터 0)이라 칩에서 제외 — 활성화 시 재추가.
const SOURCE_OPTIONS: string[] = ["narajangter", "kstartup", "ntis"];

// 지역 — 단일 시도(드롭다운). value === label. 빈 값 = 전체.
const REGION_OPTIONS: string[] = [
  "전국", "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
  "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
];

// 분야 — 단일 카테고리(드롭다운, optgroup). value === label.
// 단, 기술개발(R&D)만 백엔드 저장 형식(HTML 엔티티)을 그대로 value로 사용.
const CATEGORY_GROUPS: { label: string; options: string[] }[] = [
  { label: "입찰", options: ["용역", "공사", "물품", "외자"] },
  {
    label: "정부지원사업",
    options: [
      "사업화",
      "멘토링ㆍ컨설팅ㆍ교육",
      "시설ㆍ공간ㆍ보육",
      "행사ㆍ네트워크",
      "판로ㆍ해외진출",
      "창업교육",
      "글로벌",
      "인력",
      "정책자금",
    ],
  },
];

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
          {/* Region (지역 — 단일 선택 드롭다운) */}
          <div className="flex items-center gap-2">
            <GroupLabel>지역</GroupLabel>
            <label htmlFor="filter-region" className="sr-only">지역 선택</label>
            <select
              id="filter-region"
              value={filters.region ?? ""}
              onChange={(e) => onChange({ region: e.target.value || undefined, page: 1 })}
              className={cn(
                "h-7 rounded-lg border px-2 text-xs text-ink bg-surface",
                "focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
                filters.region
                  ? "border-primary-400 ring-1 ring-primary-200"
                  : "border-surface-border"
              )}
            >
              <option value="">전체</option>
              {REGION_OPTIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          {/* 군집 구분: 발주처 | 분류 — 시각 리듬(발견성 유지, 숨김 없음) */}
          <div aria-hidden="true" className="hidden h-7 w-px shrink-0 self-center bg-surface-border xl:block" />
          {/* Type (유형 — 계약/지원 유형 단일 선택) */}
          <div className="flex items-center gap-2">
            <GroupLabel>유형</GroupLabel>
            <label htmlFor="filter-category" className="sr-only">유형 선택</label>
            <select
              id="filter-category"
              title="계약·지원 구분(물품·용역·공사·정부지원분야)"
              value={filters.category ?? ""}
              onChange={(e) => onChange({ category: e.target.value || undefined, page: 1 })}
              className={cn(
                "h-7 rounded-lg border px-2 text-xs text-ink bg-surface",
                "focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
                filters.category
                  ? "border-primary-400 ring-1 ring-primary-200"
                  : "border-surface-border"
              )}
            >
              <option value="">전체 유형</option>
              {CATEGORY_GROUPS.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.options.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                  {g.label === "정부지원사업" && (
                    <option value={"기술개발(R&amp;D)"}>기술개발(R&D)</option>
                  )}
                </optgroup>
              ))}
            </select>
          </div>
          {/* Industry (업종 — KSIC 한국표준산업분류 대분류 단일 선택) */}
          <div className="flex items-center gap-2">
            <GroupLabel>업종</GroupLabel>
            <label htmlFor="filter-industry" className="sr-only">업종 선택</label>
            <select
              id="filter-industry"
              title="한국표준산업분류(KSIC) 업종 — 회사 산업과 매칭"
              value={filters.industry ?? ""}
              onChange={(e) => onChange({ industry: e.target.value || undefined, page: 1 })}
              className={cn(
                "h-7 rounded-lg border px-2 text-xs text-ink bg-surface",
                "focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
                filters.industry
                  ? "border-primary-400 ring-1 ring-primary-200"
                  : "border-surface-border"
              )}
            >
              <option value="">전체 업종</option>
              {KSIC_CHOICES.map((s) => (
                <option key={s.code} value={s.code}>{s.name}</option>
              ))}
            </select>
          </div>
          {/* 군집 구분: 분류 | 조건 */}
          <div aria-hidden="true" className="hidden h-7 w-px shrink-0 self-center bg-surface-border xl:block" />
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
          {/* 군집 구분: 조건 | 품질 */}
          <div aria-hidden="true" className="hidden h-7 w-px shrink-0 self-center bg-surface-border xl:block" />
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
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 focus-visible:ring-offset-1",
              activeCount > 0
                ? "text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-500/15"
                : "text-ink-400 hover:bg-surface-muted"
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
      {/* 지역 필터 정직성 — 공고의 다수는 지역 미표기라 선택 시 제외됨을 명시. */}
      {filters.region && (
        <p className="border-t border-surface-border px-4 py-1.5 text-[11px] text-ink-400">
          ‘{filters.region}’ 지역 필터 — 지역이 표기된 공고와 ‘전국’ 공고만 노출됩니다(지역 미표기 공고는 제외).
        </p>
      )}
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
  if (filters.region) n++;
  if (filters.category) n++;
  if (filters.industry) n++;
  if (filters.budget_min != null || filters.budget_max != null) n++;
  if (filters.deadline_before) n++;
  if (filters.min_score != null) n++;
  if (filters.feasibility) n++;
  if (filters.sources && filters.sources.length) n++;
  return n;
}
