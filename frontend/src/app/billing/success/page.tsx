"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { subscribe } from "@/lib/api/billing";

function BillingSuccessInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [state, setState] = useState<"loading" | "done" | "error">("loading");
  const [message, setMessage] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // StrictMode 이중 실행 방지(빌링 1회만)
    ran.current = true;

    const authKey = params.get("authKey");
    const customerKey = params.get("customerKey");
    if (!authKey || !customerKey) {
      setState("error");
      setMessage("인증 정보(authKey/customerKey)가 없습니다.");
      return;
    }
    subscribe(authKey, customerKey)
      .then((s) => {
        setState("done");
        setMessage(
          s.status === "active"
            ? "구독이 활성화되었습니다. 매일 아침 맞춤 공고를 받아보세요."
            : `구독 상태: ${s.status}`
        );
      })
      .catch(() => {
        setState("error");
        setMessage("구독 처리에 실패했습니다. 잠시 후 다시 시도해 주세요.");
      });
  }, [params]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div
        role="status"
        aria-live="polite"
        className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-8 shadow-sm text-center"
      >
        {state === "loading" && (
          <>
            <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-primary-600" />
            <p className="text-sm text-gray-600">결제 정보를 확인하고 있습니다…</p>
          </>
        )}
        {state === "done" && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
              <svg className="h-6 w-6 text-green-600" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
            </div>
            <h1 className="text-lg font-semibold text-gray-900 mb-1">구독 완료</h1>
            <p className="text-sm text-gray-600 mb-6">{message}</p>
            <Button className="w-full" onClick={() => router.push("/dashboard")}>
              대시보드로 이동
            </Button>
          </>
        )}
        {state === "error" && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <span className="text-xl text-red-600">!</span>
            </div>
            <h1 className="text-lg font-semibold text-gray-900 mb-1">구독 처리 실패</h1>
            <p className="text-sm text-gray-600 mb-6">{message}</p>
            <Button variant="secondary" className="w-full" onClick={() => router.push("/settings")}>
              설정으로 돌아가기
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

export default function BillingSuccessPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <BillingSuccessInner />
    </Suspense>
  );
}
