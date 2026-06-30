// ────────────────────────────────────────────────────────────────────────────
// WaterNature AI — API Types (mirrors backend pydantic schemas exactly)
// ────────────────────────────────────────────────────────────────────────────

// Auth — login/register/refresh return only the access token in the body;
// the refresh token is delivered as an httpOnly cookie (never exposed to JS).
export interface TokenOut {
  access_token: string;
  token_type: string;
}

export interface RegisterIn {
  email: string;
  password: string;
  company_name: string;
}

export interface LoginIn {
  email: string;
  password: string;
}

// Feasibility verdict (Go/No-Go)
export interface FeasibilityVerdict {
  verdict: "go" | "review" | "no_go";
  label: string;
  reasons: string[];
}

// Opportunity / Recommendation
export interface RecommendationItem {
  opportunity_id: string;
  title: string;
  agency: string | null;
  category: string | null; // 유형(물품·용역·공사·지원분야)
  industry: string | null; // 표준 업종 KSIC 코드(lib/ksic ksicName으로 라벨)
  budget_amount: number | null;
  deadline: string | null; // ISO datetime string
  d_day: number | null;
  score: number | null;
  reasons: string[];
  saved: boolean;
  source: string;
  other_sources: string[];
  detail_url: string | null;
  feasibility?: FeasibilityVerdict | null;
  posted_at?: string | null; // ISO datetime string (posting/registration date)
  matched_keywords?: string[]; // 키워드 워치(#5) 피드에서 매칭된 키워드
  // 설명력: 적합도 차원별 분해 + 리스크 한 줄
  subscore?: {
    tech?: number;
    track?: number;
    customer?: number;
    industry?: number;
    region?: number;
  } | null;
  risk?: string | null;
}

export interface OpportunityList {
  items: RecommendationItem[];
  total: number;
  page: number;
  size: number;
}

export type ActionType = "opened" | "reviewed" | "saved" | "participated";

export interface ActionIn {
  type: ActionType;
}

// Dashboard Stats
export interface StatsOut {
  recommended: number;
  opened: number;
  saved: number;
  participated: number;
  rates: {
    open: number;
    save: number;
    participate: number;
  };
}

// Opportunity Detail
export interface MatchInfo {
  score: number | null;
  reasons: string[];
  subscore: Record<string, number> | null;
  risk: string | null;
}

export interface OpportunityDetail {
  opportunity: {
    id: string;
    title: string;
    agency: string | null;
    category: string | null;
    budget_amount: number | null;
    deadline: string | null;
    detail_url: string | null;
    source: string;
    status: string;
    posted_at?: string | null;
    description?: string | null;
    region?: string | null;
  };
  match: MatchInfo | null;
  other_sources: string[];
  feasibility?: FeasibilityVerdict | null;
}

// Company Profile
export interface CompanyProfile {
  name?: string | null;
  industry?: string | null;
  description?: string | null;
  region?: string | null;
  phone?: string | null;
  onboarding_status?: string | null;
  services?: string[] | null;
  technologies?: string[] | null;
  customers?: string[] | null;
  certifications?: string[] | null;
  document_filename?: string | null;
  tech_level?: number | null;
  max_project_budget?: number | null;
  capable_categories?: string[] | null;
  capable_industries?: string[] | null; // 수행 업종 KSIC 코드
}

export interface CompanyCapabilityIn {
  tech_level?: number | null;
  max_project_budget?: number | null;
  capable_categories?: string[] | null;
  capable_industries?: string[] | null; // 수행 업종 KSIC 코드
}

// Notification Settings
export interface NotificationSetting {
  enabled: boolean;
  channel: string;
  send_hour: number;
  send_empty: boolean;
  // 맞춤 알림 규칙(#4)
  min_score: number | null;
  excluded_sources: string[];
  available_sources?: string[];
  // 마감 리마인더(D-3): null=기본 3, 0=끄기
  deadline_reminder_days: number | null;
}

export interface NotificationSettingIn {
  enabled?: boolean;
  channel?: string;
  send_hour?: number;
  send_empty?: boolean;
  min_score?: number | null;
  excluded_sources?: string[];
  deadline_reminder_days?: number | null;
}

// Billing
export interface BillingStatus {
  status: string;
  plan_code: string | null;
  current_period_end?: string | null;
}

// Sort
export type SortKey = "score" | "deadline" | "posted" | "budget" | "feasibility";

// Filters
export interface OpportunityFilters {
  agency?: string;
  sources?: string[]; // 출처 코드 다중선택(없음/빈배열 = 전체)
  region?: string; // 지역(단일 시도 문자열)
  category?: string; // 유형(단일 정확 카테고리 문자열: 물품·용역·공사·지원분야)
  industry?: string; // 표준 업종(KSIC 대분류 코드)
  budget_min?: number;
  budget_max?: number;
  deadline_before?: string;
  min_score?: number;
  feasibility?: "go" | "review" | "no_go";
  sort?: SortKey;
  page?: number;
  size?: number;
}

// Awards (낙찰 결과)
export interface AwardItem {
  id: string;
  title: string | null;
  category: string | null;
  winner_name: string | null;
  winner_bizno: string | null;
  award_amount: number | null;
  award_rate: number | null;
  participant_count: number | null;
  demand_agency: string | null;
  final_award_date: string | null;
  registered_at: string | null;
  bid_ntce_no: string | null;
}

export interface AwardList {
  items: AwardItem[];
  total: number;
  page: number;
  size: number;
}

// 데이터 수집 현황 (대시보드 통계 섹션)
export type TrendPeriod = "day" | "week" | "month" | "year";

export interface TrendPoint {
  label: string;
  count: number;
}

export interface SourceCount {
  source: string;
  count: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface BudgetBucket {
  label: string;
  count: number;
}

export interface BudgetStats {
  total: number;
  avg: number;
  count_with_budget: number;
  buckets: BudgetBucket[];
}

export interface AwardStats {
  count: number;
  avg_rate: number | null;
  avg_amount: number | null;
  total_amount: number | null;
}

export interface CollectionSummary {
  new_today: number;
  new_7d: number;
  total: number;
  awards_total: number;
}

export interface CollectionStats {
  as_of: string;
  summary: CollectionSummary;
  trends: Record<TrendPeriod, TrendPoint[]>;
  by_source: SourceCount[];
  by_category: CategoryCount[];
  budget: BudgetStats;
  awards: AwardStats;
}
