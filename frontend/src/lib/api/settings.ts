import { apiFetch } from "./client";
import type { NotificationSetting, NotificationSettingIn, BillingStatus, CompanyProfile, CompanyCapabilityIn } from "@/types/api";

export async function getNotificationSettings(): Promise<NotificationSetting> {
  return apiFetch<NotificationSetting>("/settings/notification");
}

export async function updateNotificationSettings(
  body: NotificationSettingIn
): Promise<void> {
  await apiFetch("/settings/notification", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function getBillingStatus(): Promise<BillingStatus> {
  return apiFetch<BillingStatus>("/settings/billing");
}

// ── 카카오 알림톡 브리핑 미리보기 ──
export interface BriefingPreviewItem {
  title: string;
  score: number | null; // 키워드-only 매칭은 점수 없음
  agency: string;
  budget: string;
  dday: string;
  source: string;
  matched_keywords?: string[];
}
export interface BriefingPreview {
  company_name: string;
  today: string;
  count: number;
  channel: string;
  send_hour: number;
  items: BriefingPreviewItem[];
  sms_fallback_text: string;
  would_send: boolean;
  blockers: string[];
  // 적용 중인 맞춤 알림 규칙(#4)
  min_score: number | null;
  excluded_sources: string[];
}

export async function getBriefingPreview(): Promise<BriefingPreview> {
  return apiFetch<BriefingPreview>("/settings/notification/preview");
}

export async function getCompanyProfile(): Promise<CompanyProfile> {
  return apiFetch<CompanyProfile>("/company/profile");
}

export async function updateCompanyCapability(body: CompanyCapabilityIn): Promise<void> {
  await apiFetch("/company/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ── LLM 공급자 설정 (시스템 전역) ──
export interface LlmModelOption {
  id: string;
  label: string;
}
export interface LlmProviderInfo {
  provider: string;
  configured: boolean;
  default_model: string;
  models: LlmModelOption[];
}
export interface LlmSettings {
  provider: string;
  model: string;
  providers: LlmProviderInfo[];
}

export async function getLlmSettings(): Promise<LlmSettings> {
  return apiFetch<LlmSettings>("/settings/llm");
}

export async function updateLlmSettings(body: {
  provider: string;
  model: string;
  api_key?: string; // 입력 시 서버에서 암호화하여 DB 저장(평문 미저장)
}): Promise<void> {
  await apiFetch("/settings/llm", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ── 카카오/SOLAPI 발신 설정 (시스템 전역 · 운영자 전용) ──
export interface KakaoConfig {
  provider: string;
  sender_key: string;          // SOLAPI 발신프로필 pfId
  template_briefing: string;   // 승인된 알림톡 템플릿 코드
  api_key_configured: boolean; // 시크릿은 값이 아닌 설정 여부만
  api_secret_configured: boolean;
  configured: boolean;
}

export async function getKakaoConfig(): Promise<KakaoConfig> {
  return apiFetch<KakaoConfig>("/settings/kakao");
}

export async function updateKakaoConfig(body: {
  provider?: string;
  sender_key?: string;
  template_briefing?: string;
  api_key?: string;    // 입력 시 서버에서 암호화하여 DB 저장(평문 미저장)
  api_secret?: string;
}): Promise<KakaoConfig> {
  return apiFetch<KakaoConfig>("/settings/kakao", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
