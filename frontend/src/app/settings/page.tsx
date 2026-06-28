"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { LoadingPage } from "@/components/ui/Spinner";
import { BillingSection } from "@/components/settings/BillingSection";
import { DocumentUploadCard } from "@/components/settings/DocumentUploadCard";
import { KakaoConfigSection } from "@/components/settings/KakaoConfigSection";
import { NotificationPreview } from "@/components/settings/NotificationPreview";
import {
  getNotificationSettings,
  updateNotificationSettings,
  getCompanyProfile,
  updateCompanyCapability,
  getLlmSettings,
  updateLlmSettings,
} from "@/lib/api/settings";
import { sourceLabel } from "@/lib/sourceLabel";
import { cn } from "@/lib/utils";
import type { NotificationSetting } from "@/types/api";

// 설정 탭 — 한 화면에 카드를 다 펼치지 않고 주제별로 분리.
const SETTINGS_TABS = [
  { key: "notify", label: "알림" },
  { key: "profile", label: "회사 프로필" },
  { key: "account", label: "계정·결제" },
] as const;
type SettingsTab = (typeof SETTINGS_TABS)[number]["key"];

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Claude (Anthropic)",
  openai: "OpenAI",
  gemini: "Google Gemini",
};

// 맞춤 알림 규칙 — 알림 적합도 임계값 옵션(빈 값 = 기본 전체).
const SCORE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "전체 추천 (기본)" },
  { value: "50", label: "적합도 50점 이상만" },
  { value: "60", label: "적합도 60점 이상만" },
  { value: "70", label: "적합도 70점 이상만" },
];

// 마감 리마인더 — 관심/진행 공고 마감 N일 전 알림(0 = 끄기).
const REMINDER_OPTIONS: { value: string; label: string }[] = [
  { value: "0", label: "끄기" },
  { value: "3", label: "D-3 (3일 전)" },
  { value: "5", label: "D-5 (5일 전)" },
  { value: "7", label: "D-7 (7일 전)" },
];

const CAPABLE_CATEGORIES = ["물품", "용역", "공사"] as const;
type CapableCategory = (typeof CAPABLE_CATEGORIES)[number];

interface CapabilityForm {
  tech_level: number | null;
  max_project_budget: string; // raw string input; parsed to number|null on submit
  capable_categories: CapableCategory[];
}

export default function SettingsPage() {
  const queryClient = useQueryClient();

  // ── Notification settings ──
  const { data: notifData, isLoading: notifLoading } = useQuery({
    queryKey: ["settings", "notification"],
    queryFn: getNotificationSettings,
  });

  const [tab, setTab] = useState<SettingsTab>("notify");

  const [notifForm, setNotifForm] = useState<NotificationSetting>({
    enabled: true,
    channel: "alimtalk",
    send_hour: 8,
    send_empty: false,
    min_score: null,
    excluded_sources: [],
    deadline_reminder_days: null,
  });
  const [notifSaved, setNotifSaved] = useState(false);

  useEffect(() => {
    if (notifData) setNotifForm(notifData);
  }, [notifData]);

  const notifMutation = useMutation({
    mutationFn: updateNotificationSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "notification"] });
      // 규칙 변경 → 알림 미리보기 + 마감 임박 갱신.
      queryClient.invalidateQueries({ queryKey: ["notification", "preview"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
      setNotifSaved(true);
      setTimeout(() => setNotifSaved(false), 2500);
    },
  });

  function toggleExcludedSource(src: string) {
    setNotifForm((f) => {
      const excluded = f.excluded_sources ?? [];
      return {
        ...f,
        excluded_sources: excluded.includes(src)
          ? excluded.filter((s) => s !== src)
          : [...excluded, src],
      };
    });
  }

  function handleNotifSubmit(e: React.FormEvent) {
    e.preventDefault();
    notifMutation.mutate(notifForm);
  }

  // ── Company capability settings ──
  const { data: profileData, isLoading: profileLoading } = useQuery({
    queryKey: ["company", "profile"],
    queryFn: getCompanyProfile,
  });

  const [capForm, setCapForm] = useState<CapabilityForm>({
    tech_level: null,
    max_project_budget: "",
    capable_categories: [],
  });
  const [capSaved, setCapSaved] = useState(false);

  useEffect(() => {
    if (profileData) {
      setCapForm({
        tech_level: profileData.tech_level ?? null,
        max_project_budget:
          profileData.max_project_budget != null
            ? String(profileData.max_project_budget)
            : "",
        capable_categories: (profileData.capable_categories ?? []) as CapableCategory[],
      });
    }
  }, [profileData]);

  const capMutation = useMutation({
    mutationFn: updateCompanyCapability,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["company", "profile"] });
      // Invalidate recommendations — feasibility is recalculated server-side
      queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
      setCapSaved(true);
      setTimeout(() => setCapSaved(false), 2500);
    },
  });

  function handleCapSubmit(e: React.FormEvent) {
    e.preventDefault();
    const budgetRaw = capForm.max_project_budget.replace(/,/g, "").trim();
    const budget = budgetRaw !== "" ? Number(budgetRaw) : null;
    capMutation.mutate({
      tech_level: capForm.tech_level,
      max_project_budget: budget,
      capable_categories: capForm.capable_categories.length > 0 ? capForm.capable_categories : null,
    });
  }

  function toggleCategory(cat: CapableCategory) {
    setCapForm((prev) => ({
      ...prev,
      capable_categories: prev.capable_categories.includes(cat)
        ? prev.capable_categories.filter((c) => c !== cat)
        : [...prev.capable_categories, cat],
    }));
  }

  // ── LLM provider settings (system-wide) ──
  const { data: llmData, isLoading: llmLoading } = useQuery({
    queryKey: ["settings", "llm"],
    queryFn: getLlmSettings,
  });

  const [llmProvider, setLlmProvider] = useState<string>("");
  const [llmModel, setLlmModel] = useState<string>("");
  const [llmApiKey, setLlmApiKey] = useState<string>("");
  const [llmSaved, setLlmSaved] = useState(false);

  useEffect(() => {
    if (llmData) {
      setLlmProvider(llmData.provider);
      setLlmModel(llmData.model);
    }
  }, [llmData]);

  const selectedProviderInfo = llmData?.providers.find((p) => p.provider === llmProvider);
  const selectedConfigured = selectedProviderInfo?.configured ?? false;
  // 저장 가능: 기존 키가 있거나(설정됨) 새 키를 입력 중일 때
  const canSaveLlm = selectedConfigured || llmApiKey.trim().length > 0;

  const llmMutation = useMutation({
    mutationFn: updateLlmSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "llm"] });
      // 매칭 근거는 다음 매칭부터 LLM이 생성 — 추천 캐시 무효화
      queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
      setLlmApiKey("");
      setLlmSaved(true);
      setTimeout(() => setLlmSaved(false), 2500);
    },
  });

  function handleProviderChange(provider: string) {
    setLlmProvider(provider);
    setLlmApiKey("");
    const info = llmData?.providers.find((p) => p.provider === provider);
    // 공급자 변경 시 모델을 해당 공급자 기본값(없으면 첫 모델)으로
    setLlmModel(info?.default_model || info?.models[0]?.id || "");
  }

  function handleLlmSubmit(e: React.FormEvent) {
    e.preventDefault();
    const key = llmApiKey.trim();
    llmMutation.mutate({
      provider: llmProvider,
      model: llmModel,
      api_key: key.length > 0 ? key : undefined,
    });
  }

  // Alias for backward-compat with existing JSX that used `form` / `setForm`
  const form = notifForm;
  const setForm = setNotifForm;

  if (notifLoading || profileLoading || llmLoading) return <LoadingPage />;

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink">설정</h1>
        <p className="mt-0.5 text-sm text-gray-500">알림 및 계정 설정을 관리합니다</p>
      </div>

      {/* 설정 탭 — 한 화면에 다 펼치지 않고 주제별로 전환 */}
      <div
        className="mb-5 flex gap-1 overflow-x-auto border-b border-surface-border"
        role="tablist"
        aria-label="설정 보기"
      >
        {SETTINGS_TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            id={`settings-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`settings-panel-${t.key}`}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px whitespace-nowrap rounded-t border-b-2 px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
              tab === t.key
                ? "border-primary-600 text-primary-700"
                : "border-transparent text-ink-400 hover:border-surface-border hover:text-ink-600"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="max-w-xl">
        {tab === "account" && (
          <div
            id="settings-panel-account"
            role="tabpanel"
            aria-labelledby="settings-tab-account"
            className="space-y-6"
          >
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wide text-ink-400">계정·시스템</h2>
              <p className="mt-0.5 text-xs text-gray-400">AI 공급자 키와 구독을 관리합니다.</p>
            </div>

            {/* AI 공급자 (LLM) settings card */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-1">AI 공급자</h2>
          <p className="text-sm text-gray-500 mb-5">
            추천 적합도·근거 생성에 쓸 LLM 공급자·모델을 고르고 API 키를 입력합니다. 키는
            <span className="mx-1 font-medium text-gray-600">암호화되어 DB에 저장</span>되며
            화면에 다시 노출되지 않습니다.
          </p>

          <form onSubmit={handleLlmSubmit} className="space-y-5">
            {/* Provider */}
            <div>
              <label htmlFor="llm-provider" className="block text-sm font-medium text-gray-700 mb-1.5">공급자</label>
              <select
                id="llm-provider"
                value={llmProvider}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              >
                {llmData?.providers.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {PROVIDER_LABELS[p.provider] ?? p.provider}
                    {p.configured ? " ✓ 키 설정됨" : " (키 미설정)"}
                  </option>
                ))}
              </select>
            </div>

            {/* Model */}
            <div>
              <label htmlFor="llm-model" className="block text-sm font-medium text-gray-700 mb-1.5">모델</label>
              <select
                id="llm-model"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              >
                {selectedProviderInfo?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>

            {/* API key (암호화 후 DB 저장) */}
            <div>
              <label htmlFor="llm-apikey" className="block text-sm font-medium text-gray-700 mb-1.5">
                API 키
                {selectedConfigured && (
                  <span className="ml-2 text-xs font-normal text-emerald-600">✓ 설정됨</span>
                )}
              </label>
              <input
                id="llm-apikey"
                type="password"
                value={llmApiKey}
                onChange={(e) => setLlmApiKey(e.target.value)}
                placeholder={selectedConfigured ? "변경하려면 새 키 입력 (비우면 현재 키 유지)" : "sk-... 키 입력"}
                autoComplete="off"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
              <p className="mt-1.5 text-xs text-gray-500">
                입력한 키는 서버에서 <span className="text-gray-600">암호화되어 DB에 저장</span>되며,
                저장 후 화면에 다시 표시되지 않습니다.
              </p>
            </div>

            {llmMutation.isError && (
              <Alert variant="error">저장 실패 — 키가 올바른지 확인하세요.</Alert>
            )}

            <div className="flex items-center gap-3">
              <Button type="submit" loading={llmMutation.isPending} disabled={!canSaveLlm}>
                저장
              </Button>
              {llmSaved && (
                <span className="text-sm text-emerald-600 font-medium flex items-center gap-1.5">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  저장되었습니다
                </span>
              )}
            </div>
          </form>
        </div>

        {/* 카카오 발신 자격증명 (SOLAPI) — 시스템 전역·운영자 전용 */}
        <KakaoConfigSection />

        {/* Billing & subscription */}
        <BillingSection />
          </div>
        )}

        {tab === "notify" && (
          <div
            id="settings-panel-notify"
            role="tabpanel"
            aria-labelledby="settings-tab-notify"
            className="space-y-6"
          >
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wide text-ink-400">알림</h2>
              <p className="mt-0.5 text-xs text-gray-400">
                맞춤 알림 규칙·마감 리마인더와 브리핑 미리보기. 내 공고:
                <a href="/saved" className="ml-1 font-medium text-primary-600 hover:underline">관심 공고</a>
                <span className="mx-1 text-gray-300">·</span>
                <a href="/pipeline" className="font-medium text-primary-600 hover:underline">진행 관리</a>
                <span className="mx-1 text-gray-300">·</span>
                <a href="/opportunities?tab=watch" className="font-medium text-primary-600 hover:underline">키워드 워치</a>
              </p>
            </div>

        {/* Notification settings card */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-1">알림 설정</h2>
          <p className="text-sm text-gray-500 mb-5">
            매일 AI 추천 공고를 받아볼 채널과 시간을 설정합니다.
          </p>

          <form onSubmit={handleNotifSubmit} className="space-y-5">
            {/* Enabled toggle */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">알림 활성화</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  오늘의 추천 공고를 매일 알림으로 받습니다
                </p>
              </div>
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, enabled: !f.enabled }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${
                  form.enabled ? "bg-primary-600" : "bg-gray-200"
                }`}
                role="switch"
                aria-checked={form.enabled}
                aria-label="알림 활성화"
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    form.enabled ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>

            {/* Channel */}
            <fieldset>
              <legend className="block text-sm font-medium text-gray-700 mb-1.5">알림 채널</legend>
              <div className="flex gap-3">
                {["alimtalk", "email"].map((ch) => (
                  <label key={ch} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="channel"
                      value={ch}
                      checked={form.channel === ch}
                      onChange={() => setForm((f) => ({ ...f, channel: ch }))}
                      className="h-4 w-4 text-primary-600 border-gray-300 focus:ring-primary-500"
                    />
                    <span className="text-sm text-gray-700">
                      {ch === "alimtalk" ? "카카오 알림톡" : "이메일"}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            {/* Send hour */}
            <div>
              <label htmlFor="notif-send-hour" className="block text-sm font-medium text-gray-700 mb-1.5">
                발송 시각 (KST)
              </label>
              <select
                id="notif-send-hour"
                value={form.send_hour}
                onChange={(e) => setForm((f) => ({ ...f, send_hour: parseInt(e.target.value) }))}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 sm:w-40"
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>
                    {String(i).padStart(2, "0")}:00
                  </option>
                ))}
              </select>
            </div>

            {/* Send empty */}
            <div className="flex items-center gap-3">
              <input
                id="send_empty"
                type="checkbox"
                checked={form.send_empty}
                onChange={(e) => setForm((f) => ({ ...f, send_empty: e.target.checked }))}
                className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label htmlFor="send_empty" className="text-sm text-gray-700">
                추천 공고 없을 때도 알림 발송
              </label>
            </div>

            {/* 맞춤 알림 규칙(#4) — 적합도 임계값 + 출처 선택 */}
            <div className="space-y-4 rounded-lg border border-surface-border bg-surface/60 p-4">
              <div>
                <p className="text-sm font-medium text-gray-700">맞춤 알림 규칙</p>
                <p className="mt-0.5 text-xs text-gray-500">
                  알림에 담을 추천의 최소 적합도와 공고 출처를 정합니다. 미리보기에 바로 반영됩니다.
                </p>
              </div>

              {/* 최소 적합도 */}
              <div>
                <label htmlFor="notif-min-score" className="block text-sm font-medium text-gray-700 mb-1.5">
                  알림 최소 적합도
                </label>
                <select
                  id="notif-min-score"
                  value={form.min_score == null ? "" : String(form.min_score)}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      min_score: e.target.value === "" ? null : Number(e.target.value),
                    }))
                  }
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                >
                  {SCORE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1.5 text-xs text-gray-400">
                  높일수록 더 잘 맞는 공고만 적게 받습니다.
                </p>
              </div>

              {/* 알림 받을 출처 */}
              <fieldset>
                <legend className="block text-sm font-medium text-gray-700 mb-2">
                  알림 받을 공고 출처
                </legend>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {(form.available_sources ?? ["narajangter", "kstartup", "ntis"]).map((src) => {
                    const included = !(form.excluded_sources ?? []).includes(src);
                    return (
                      <label key={src} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={included}
                          onChange={() => toggleExcludedSource(src)}
                          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">{sourceLabel(src)}</span>
                      </label>
                    );
                  })}
                </div>
                <p className="mt-1.5 text-xs text-gray-400">
                  체크를 해제한 출처의 공고는 알림에서 제외됩니다.
                </p>
              </fieldset>

              {/* 마감 리마인더(D-3) */}
              <div>
                <label htmlFor="notif-reminder-days" className="block text-sm font-medium text-gray-700 mb-1.5">
                  마감 리마인더
                </label>
                <select
                  id="notif-reminder-days"
                  value={form.deadline_reminder_days == null ? "3" : String(form.deadline_reminder_days)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, deadline_reminder_days: Number(e.target.value) }))
                  }
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                >
                  {REMINDER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1.5 text-xs text-gray-400">
                  관심·진행 공고의 마감이 가까우면 대시보드 ‘마감 임박’과 알림으로 알려드려요.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button type="submit" loading={notifMutation.isPending}>
                저장
              </Button>
              {notifSaved && (
                <span className="text-sm text-emerald-600 font-medium flex items-center gap-1.5">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  저장되었습니다
                </span>
              )}
              {notifMutation.isError && (
                <span className="text-sm font-medium text-red-600">저장에 실패했습니다. 다시 시도해 주세요.</span>
              )}
            </div>
          </form>
        </div>

        {/* Kakao briefing preview */}
        <NotificationPreview />
          </div>
        )}

        {tab === "profile" && (
          <div
            id="settings-panel-profile"
            role="tabpanel"
            aria-labelledby="settings-tab-profile"
            className="space-y-6"
          >
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wide text-ink-400">회사 프로필</h2>
              <p className="mt-0.5 text-xs text-gray-400">수행 역량과 회사소개서로 추천 정확도를 높입니다.</p>
            </div>

        {/* Capability settings card */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-1">수행 역량</h2>
          <p className="text-sm text-gray-500 mb-5">
            역량을 설정하면 AI가 각 공고의 수행 가능성(Go/No-Go)을 판단합니다.
          </p>

          <form onSubmit={handleCapSubmit} className="space-y-5">
            {/* Tech level */}
            <div>
              <span id="cap-tech-label" className="block text-sm font-medium text-gray-700 mb-2">
                기술 수준 (1~5)
              </span>
              <div className="flex gap-2" role="group" aria-labelledby="cap-tech-label">
                {([1, 2, 3, 4, 5] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() =>
                      setCapForm((f) => ({
                        ...f,
                        tech_level: f.tech_level === level ? null : level,
                      }))
                    }
                    className={`h-9 w-9 rounded-lg text-sm font-semibold border transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 ${
                      capForm.tech_level === level
                        ? "border-primary-600 bg-primary-600 text-white"
                        : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                    }`}
                    aria-pressed={capForm.tech_level === level}
                  >
                    {level}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-400">
                1: 초급 · 3: 중급 · 5: 전문가 수준
              </p>
            </div>

            {/* Max project budget */}
            <div>
              <label htmlFor="cap-budget" className="block text-sm font-medium text-gray-700 mb-1.5">
                수행 가능 최대 사업 규모
                <span className="ml-1.5 text-xs text-gray-500 font-normal">(원 단위, 빈 값 = 제한 없음)</span>
              </label>
              <div className="relative">
                <input
                  id="cap-budget"
                  type="text"
                  inputMode="numeric"
                  value={capForm.max_project_budget}
                  onChange={(e) =>
                    setCapForm((f) => ({ ...f, max_project_budget: e.target.value }))
                  }
                  placeholder="예: 500000000 (5억원)"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 pr-12"
                />
                <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-gray-400">
                  원
                </span>
              </div>
              {capForm.max_project_budget && !isNaN(Number(capForm.max_project_budget.replace(/,/g, ""))) && (
                <p className="mt-1 text-xs text-gray-400">
                  {(Number(capForm.max_project_budget.replace(/,/g, "")) / 100000000).toFixed(1)}억원
                </p>
              )}
            </div>

            {/* Capable categories */}
            <fieldset>
              <legend className="block text-sm font-medium text-gray-700 mb-2">
                수행 가능 유형
              </legend>
              <div className="flex gap-3">
                {CAPABLE_CATEGORIES.map((cat) => (
                  <label key={cat} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={capForm.capable_categories.includes(cat)}
                      onChange={() => toggleCategory(cat)}
                      className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm text-gray-700">{cat}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="flex items-center gap-3">
              <Button type="submit" loading={capMutation.isPending}>
                역량 저장
              </Button>
              {capSaved && (
                <span className="text-sm text-emerald-600 font-medium flex items-center gap-1.5">
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  저장되었습니다
                </span>
              )}
              {capMutation.isError && (
                <span className="text-sm font-medium text-red-600">저장에 실패했습니다. 다시 시도해 주세요.</span>
              )}
            </div>
          </form>
        </div>

        {/* 회사소개서 재업로드 */}
        <DocumentUploadCard currentFilename={profileData?.document_filename} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
