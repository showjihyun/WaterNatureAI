"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";

function BillingFailInner() {
  const params = useSearchParams();
  const router = useRouter();
  const reason = params.get("message") || params.get("code") || "결제가 취소되었거나 실패했습니다.";

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-muted px-4">
      <div className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-8 shadow-sm text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-500/20">
          <span className="text-xl text-red-600 dark:text-red-300">!</span>
        </div>
        <h1 className="text-lg font-semibold text-ink mb-1">결제를 완료하지 못했습니다</h1>
        <p className="text-sm text-ink-600 mb-6">{reason}</p>
        <Button variant="secondary" className="w-full" onClick={() => router.push("/settings")}>
          설정으로 돌아가기
        </Button>
      </div>
    </div>
  );
}

export default function BillingFailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface-muted" />}>
      <BillingFailInner />
    </Suspense>
  );
}
