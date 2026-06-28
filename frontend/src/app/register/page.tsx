"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Wordmark, BrandMark } from "@/components/ui/Brand";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    email: "",
    password: "",
    passwordConfirm: "",
    company_name: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (form.password !== form.passwordConfirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }
    if (form.password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    setLoading(true);
    try {
      await register({
        email: form.email,
        password: form.password,
        company_name: form.company_name,
      });
      router.push("/onboarding");
    } catch (err) {
      let msg = "회원가입에 실패했습니다. 잠시 후 다시 시도해 주세요.";
      if (err instanceof ApiError) {
        if (err.status === 409) msg = "이미 사용 중인 이메일입니다.";
        else if (err.status === 429) msg = "요청이 많습니다. 잠시 후 다시 시도해 주세요.";
        else if (err.status === 422) msg = "입력값을 다시 확인해 주세요.";
      }
      setError(msg);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-primary-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="inline-flex items-center gap-2">
            <span className="text-primary-600">
              <BrandMark className="h-6 w-6" />
            </span>
            <Wordmark tone="light" className="text-2xl" />
          </span>
          <p className="mt-2 text-sm text-gray-500">무료로 시작하세요</p>
        </div>

        <div className="rounded-2xl border border-surface-border bg-surface-card p-8 shadow-sm">
          <h1 className="mb-6 text-xl font-semibold text-gray-900">회원가입</h1>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="reg-company" className="block text-sm font-medium text-gray-700 mb-1.5">
                회사명
              </label>
              <input
                id="reg-company"
                name="company_name"
                type="text"
                autoComplete="organization"
                required
                value={form.company_name}
                onChange={handleChange}
                placeholder="(주)우리회사"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>

            <div>
              <label htmlFor="reg-email" className="block text-sm font-medium text-gray-700 mb-1.5">
                이메일
              </label>
              <input
                id="reg-email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={form.email}
                onChange={handleChange}
                placeholder="admin@company.com"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>

            <div>
              <label htmlFor="reg-password" className="block text-sm font-medium text-gray-700 mb-1.5">
                비밀번호 <span className="text-gray-500 font-normal">(8자 이상)</span>
              </label>
              <input
                id="reg-password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={form.password}
                onChange={handleChange}
                placeholder="••••••••"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>

            <div>
              <label htmlFor="reg-password-confirm" className="block text-sm font-medium text-gray-700 mb-1.5">
                비밀번호 확인
              </label>
              <input
                id="reg-password-confirm"
                name="passwordConfirm"
                type="password"
                autoComplete="new-password"
                required
                value={form.passwordConfirm}
                onChange={handleChange}
                placeholder="••••••••"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 border border-red-200">
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} className="w-full mt-2" size="lg">
              가입하기
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-500">
            이미 계정이 있으신가요?{" "}
            <Link href="/login" className="font-medium text-primary-600 hover:underline">
              로그인
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
