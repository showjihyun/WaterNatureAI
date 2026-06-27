"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api/auth";
import { getCompanyProfile } from "@/lib/api/settings";
import { Button } from "@/components/ui/Button";
import { Wordmark, BrandMark } from "@/components/ui/Brand";

/** 물결(ripple) 모티프 — 중심에서 동심원이 퍼지는 모양(WaterNature). */
function RippleMotif() {
  return (
    <div className="relative flex items-center justify-center w-48 h-48">
      <div className="absolute inset-0 rounded-full border border-primary-400/20" />
      <div className="absolute inset-6 rounded-full border border-primary-400/30" />
      <div className="absolute inset-12 rounded-full border border-primary-400/40" />
      <div className="absolute inset-[4.5rem] rounded-full border border-primary-400/60" />
      {/* 중심에서 번지는 물결 */}
      <span className="absolute h-3 w-3 rounded-full bg-primary-400/40 animate-ping" />
      <div className="absolute h-2 w-2 rounded-full bg-primary-400" />
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ email, password });
      // 온보딩 미완성(status≠ready)이면 온보딩으로, 완료면 대시보드로.
      try {
        const profile = await getCompanyProfile();
        router.push(profile?.onboarding_status === "ready" ? "/dashboard" : "/onboarding");
      } catch {
        router.push("/dashboard"); // 프로필 조회 실패 시 대시보드(빈 상태가 안내)
      }
    } catch (err) {
      setError("이메일 또는 비밀번호가 올바르지 않습니다.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Left hero panel — desktop only */}
      <div className="hidden lg:flex lg:w-1/2 flex-col items-center justify-center bg-ink px-12 py-16 gap-10">
        {/* Wordmark */}
        <div className="text-center">
          <div className="flex items-center justify-center gap-2.5">
            <span className="text-primary-400">
              <BrandMark className="h-8 w-8" />
            </span>
            <Wordmark tone="dark" className="text-3xl" />
          </div>
          <p className="mt-1 text-xs font-medium text-primary-400/80 uppercase tracking-widest">
            AI 공공사업 추천
          </p>
        </div>

        {/* Ripple motif */}
        <RippleMotif />

        {/* Value prop */}
        <div className="text-center max-w-xs">
          <p className="text-lg font-semibold text-white leading-snug">
            매일 아침, 우리 회사가 딸 수 있는<br />공공 사업만 골라 드립니다.
          </p>
          <p className="mt-3 text-sm text-slate-400 leading-relaxed">
            AI가 역량 프로필을 분석해 적합도 높은 공공조달 기회를 자동 큐레이션합니다.
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-12 bg-surface">
        {/* Mobile wordmark */}
        <div className="mb-8 text-center lg:hidden">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="text-primary-600">
              <BrandMark className="h-6 w-6" />
            </span>
            <Wordmark tone="light" className="text-xl" />
          </div>
          <p className="text-sm text-slate-500">AI 공공사업 추천에 오신 것을 환영합니다</p>
        </div>

        <div className="w-full max-w-sm">
          {/* Card */}
          <div className="rounded-2xl border border-surface-border bg-surface-card p-8 shadow-sm">
            <h1 className="mb-6 text-xl font-semibold text-ink">로그인</h1>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  이메일
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="company@example.com"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  비밀번호
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {error && (
                <div className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 border border-red-200">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                loading={loading}
                className="w-full mt-2"
                size="lg"
              >
                로그인
              </Button>
            </form>

            <p className="mt-5 text-center text-sm text-gray-500">
              계정이 없으신가요?{" "}
              <Link
                href="/register"
                className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
              >
                회원가입
              </Link>
            </p>
          </div>

          {/* Demo hint */}
          <p className="mt-4 text-center text-xs text-gray-400">
            데모 확인:{" "}
            <Link href="/dashboard?mock=1" className="text-primary-500 underline">
              목 데이터 대시보드 바로가기
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
