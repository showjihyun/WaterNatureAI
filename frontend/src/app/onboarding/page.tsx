"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Wordmark, BrandMark } from "@/components/ui/Brand";
import { apiFetch, apiUpload, ApiError } from "@/lib/api/client";
import { getCompanyProfile } from "@/lib/api/settings";

const STEPS = [
  { id: 1, label: "회사 기본정보" },
  { id: 2, label: "사업 역량" },
  { id: 3, label: "인증 & 고객" },
  { id: 4, label: "회사소개서" },
];

interface UploadResult {
  filename: string;
  page_count: number;
  char_count: number;
  truncated: boolean;
  preview: string;
}

interface ProfileForm {
  company_name: string;
  industry: string;
  description: string;
  region: string;
  services: string;
  technologies: string;
  target_customers: string;
  certifications: string;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [form, setForm] = useState<ProfileForm>({
    company_name: "",
    industry: "",
    description: "",
    region: "",
    services: "",
    technologies: "",
    target_customers: "",
    certifications: "",
  });

  // 가입 시 입력한 회사명 등 기존 프로필을 불러와 폼에 채움(재입력·공란 덮어쓰기 방지).
  useEffect(() => {
    let cancelled = false;
    getCompanyProfile()
      .then((p) => {
        if (cancelled || !p) return;
        setForm((prev) => ({
          ...prev,
          company_name: p.name ?? prev.company_name,
          industry: p.industry ?? prev.industry,
          description: p.description ?? prev.description,
          region: p.region ?? prev.region,
          services: (p.services ?? []).join(", ") || prev.services,
          technologies: (p.technologies ?? []).join(", ") || prev.technologies,
          target_customers: (p.customers ?? []).join(", ") || prev.target_customers,
          certifications: (p.certifications ?? []).join(", ") || prev.certifications,
        }));
      })
      .catch(() => {
        // 프로필 조회 실패는 비치명적 — 빈 폼으로 진행.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleNext(e: React.FormEvent) {
    e.preventDefault();
    if (step < STEPS.length) setStep((s) => s + 1);
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadResult(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const result = await apiUpload<UploadResult>("/company/documents", fd);
      setUploadResult(result);
    } catch (err) {
      const detail =
        err instanceof ApiError && err.detail && typeof err.detail === "object"
          ? (err.detail as { detail?: string }).detail
          : null;
      setUploadError(detail ?? "파일 분석에 실패했습니다. PDF 파일인지 확인해 주세요.");
    } finally {
      setUploading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload = {
        name: form.company_name,
        industry: form.industry,
        description: form.description,
        region: form.region,
        services: form.services
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        technologies: form.technologies
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        customers: form.target_customers
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        certifications: form.certifications
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      await apiFetch("/company/profile", { method: "PUT", body: JSON.stringify(payload) });
      // brain 생성 = status→ready·매칭 트리거. 실패하면 추천이 영영 안 뜨므로 silent 금지 —
      // 알리고 재시도 유도('완료' 재클릭 시 PUT은 멱등, brain만 다시 시도됨).
      try {
        await apiFetch("/company/brain", { method: "POST" });
      } catch {
        setError(
          "프로필은 저장됐어요. 다만 AI 분석 시작에 실패했습니다. 잠시 후 '완료'를 다시 눌러 주세요."
        );
        setLoading(false);
        return;
      }
      router.push("/dashboard");
    } catch {
      setError("프로필 저장에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="sr-only">회사 프로필 등록</h1>
          <span className="inline-flex items-center gap-2">
            <span className="text-primary-600">
              <BrandMark className="h-5 w-5" />
            </span>
            <Wordmark tone="light" className="text-xl" />
          </span>
          <p className="mt-2 text-sm text-gray-500">
            회사 프로필을 등록하면 AI가 맞춤 공고를 추천해 드립니다
          </p>
        </div>

        {/* Progress */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center">
                <div
                  aria-current={step === s.id ? "step" : undefined}
                  aria-label={`${STEPS.length}단계 중 ${s.id}단계: ${s.label}`}
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                    step > s.id
                      ? "bg-primary-600 text-white"
                      : step === s.id
                      ? "border-2 border-primary-600 text-primary-600"
                      : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {step > s.id ? (
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    s.id
                  )}
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={`mx-1.5 h-0.5 w-14 transition-colors ${
                      step > s.id ? "bg-primary-600" : "bg-gray-200"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs text-gray-500">
            {STEPS.map((s) => (
              <span key={s.id} className={step === s.id ? "text-primary-600 font-medium" : ""}>
                {s.label}
              </span>
            ))}
          </div>
        </div>

        {/* Form card */}
        <div className="rounded-2xl border border-surface-border bg-surface-card p-8 shadow-sm">
          {step === 1 && (
            <form onSubmit={handleNext} className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-5">회사 기본정보</h2>
              <div>
                <label htmlFor="ob-company" className="block text-sm font-medium text-gray-700 mb-1.5">회사명</label>
                <input
                  id="ob-company"
                  name="company_name"
                  required
                  value={form.company_name}
                  onChange={handleChange}
                  placeholder="(주)우리회사"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
              <div>
                <label htmlFor="ob-industry" className="block text-sm font-medium text-gray-700 mb-1.5">업종</label>
                <select
                  id="ob-industry"
                  name="industry"
                  value={form.industry}
                  onChange={handleChange}
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                >
                  <option value="">선택하세요</option>
                  <option value="IT서비스">IT서비스</option>
                  <option value="소프트웨어">소프트웨어</option>
                  <option value="AI/데이터">AI/데이터</option>
                  <option value="SI/공공">SI/공공</option>
                  <option value="환경/에너지">환경/에너지</option>
                  <option value="건설/엔지니어링">건설/엔지니어링</option>
                  <option value="제조">제조</option>
                  <option value="연구/R&D">연구/R&D</option>
                  <option value="의료/바이오">의료/바이오</option>
                  <option value="교육">교육</option>
                  <option value="컨설팅">컨설팅</option>
                  <option value="기타">기타</option>
                </select>
              </div>
              <div>
                <label htmlFor="ob-description" className="block text-sm font-medium text-gray-700 mb-1.5">사업 소개</label>
                <textarea
                  id="ob-description"
                  name="description"
                  value={form.description}
                  onChange={handleChange}
                  rows={3}
                  placeholder="회사의 주요 사업을 간략히 설명해 주세요"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 resize-none"
                />
              </div>
              <div>
                <label htmlFor="ob-region" className="block text-sm font-medium text-gray-700 mb-1.5">주요 활동 지역</label>
                <input
                  id="ob-region"
                  name="region"
                  value={form.region}
                  onChange={handleChange}
                  placeholder="수도권, 전국, 경기도 등"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
              <Button type="submit" className="w-full mt-2" size="lg">
                다음 단계
              </Button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleNext} className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-5">사업 역량</h2>
              <div>
                <label htmlFor="ob-services" className="block text-sm font-medium text-gray-700 mb-1.5">
                  주요 서비스/제품
                  <span className="text-gray-500 font-normal ml-1">(쉼표로 구분)</span>
                </label>
                <input
                  id="ob-services"
                  name="services"
                  required
                  value={form.services}
                  onChange={handleChange}
                  placeholder="예: 수처리 시설 시공, 클라우드 구축, 교육 콘텐츠 개발"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
              <div>
                <label htmlFor="ob-technologies" className="block text-sm font-medium text-gray-700 mb-1.5">
                  보유 기술 스택
                  <span className="text-gray-500 font-normal ml-1">(쉼표로 구분)</span>
                </label>
                <input
                  id="ob-technologies"
                  name="technologies"
                  value={form.technologies}
                  onChange={handleChange}
                  placeholder="예: MBR 막여과, 구조설계, Python, IoT 센서"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
              <div className="flex gap-3">
                <Button type="button" variant="secondary" className="flex-1" onClick={() => setStep(1)}>
                  이전
                </Button>
                <Button type="submit" className="flex-1">
                  다음 단계
                </Button>
              </div>
            </form>
          )}

          {step === 3 && (
            <form onSubmit={handleNext} className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-5">인증 & 고객</h2>
              <div>
                <label htmlFor="ob-customers" className="block text-sm font-medium text-gray-700 mb-1.5">
                  주요 고객사 유형
                  <span className="text-gray-500 font-normal ml-1">(쉼표로 구분)</span>
                </label>
                <input
                  id="ob-customers"
                  name="target_customers"
                  value={form.target_customers}
                  onChange={handleChange}
                  placeholder="중소기업, 공공기관, 대기업 계열사"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
              <div>
                <label htmlFor="ob-certifications" className="block text-sm font-medium text-gray-700 mb-1.5">
                  보유 인증
                  <span className="text-gray-500 font-normal ml-1">(쉼표로 구분)</span>
                </label>
                <input
                  id="ob-certifications"
                  name="certifications"
                  value={form.certifications}
                  onChange={handleChange}
                  placeholder="ISO 9001, GS인증, ISMS, Inno-Biz, 기업부설연구소"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>

              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  className="flex-1"
                  onClick={() => setStep(2)}
                >
                  이전
                </Button>
                <Button type="submit" className="flex-1">
                  다음 단계
                </Button>
              </div>
            </form>
          )}

          {step === 4 && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">회사소개서 업로드</h2>
              <p className="text-sm text-gray-500 mb-4">
                회사소개서 PDF를 올리면 AI가 문서를 읽고 역량·실적을 더 정확히 분석합니다.
                <span className="text-gray-400"> (선택 — 건너뛰어도 됩니다)</span>
              </p>

              <label
                htmlFor="brochure"
                className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-gray-300 px-4 py-8 cursor-pointer hover:border-primary-400 hover:bg-primary-50/30 transition-colors"
              >
                <svg className="h-8 w-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
                </svg>
                <span className="text-sm font-medium text-gray-700">
                  {uploading ? "분석 중…" : "PDF 파일 선택 또는 드래그"}
                </span>
                <span className="text-xs text-gray-400">최대 20MB · PDF</span>
                <input
                  id="brochure"
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  disabled={uploading}
                  onChange={handleFileChange}
                />
              </label>

              {uploadResult && (
                <div className="rounded-lg bg-green-50 px-3 py-2.5 text-sm text-green-800 border border-green-200">
                  <p className="font-medium">✓ {uploadResult.filename} 분석 완료</p>
                  <p className="text-xs text-green-700 mt-0.5">
                    {uploadResult.page_count}페이지 · {uploadResult.char_count.toLocaleString()}자 추출
                    {uploadResult.truncated && " (일부 발췌)"}
                  </p>
                </div>
              )}

              {uploadError && (
                <div className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 border border-red-200">
                  {uploadError}
                </div>
              )}

              {error && (
                <div className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 border border-red-200">
                  {error}
                </div>
              )}

              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  className="flex-1"
                  onClick={() => setStep(3)}
                >
                  이전
                </Button>
                <Button type="submit" loading={loading} disabled={uploading} className="flex-1">
                  프로필 저장하고 분석 시작
                </Button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
