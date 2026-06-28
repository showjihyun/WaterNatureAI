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
  category: string | null;
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
}

export interface CompanyCapabilityIn {
  tech_level?: number | null;
  max_project_budget?: number | null;
  capable_categories?: string[] | null;
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
  budget_min?: number;
  budget_max?: number;
  deadline_before?: string;
  min_score?: number;
  feasibility?: "go" | "review" | "no_go";
  sort?: SortKey;
  page?: number;
  size?: number;
}
