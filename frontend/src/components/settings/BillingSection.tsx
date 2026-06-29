"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import {
  getBillingConfig,
  getSubscription,
  cancelSubscription,
} from "@/lib/api/billing";
import { requestCardBillingAuth } from "@/lib/toss";

const STATUS_META: Record<string, { label: string; cls: string }> = {
  active: { label: "구독 중", cls: "bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-300" },
  trialing: { label: "체험 중", cls: "bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300" },
  past_due: { label: "결제 실패", cls: "bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300" },
  canceled: { label: "해지됨", cls: "bg-surface-muted text-ink-600" },
  none: { label: "미구독", cls: "bg-surface-muted text-ink-600" },
};

export function BillingSection() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({
    queryKey: ["billing", "config"],
    queryFn: getBillingConfig,
  });
  const { data: sub, isLoading } = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: getSubscription,
  });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cancelMutation = useMutation({
    mutationFn: cancelSubscription,
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["billing", "subscription"] });
    },
    onError: () => setError("구독 해지에 실패했습니다. 잠시 후 다시 시도해 주세요."),
  });

  async function handleSubscribe() {
    if (!config) return;
    setError(null);
    if (!config.client_key) {
      setError("결제 키가 설정되지 않았습니다 (Toss 테스트 키 필요).");
      return;
    }
    setBusy(true);
    try {
      // Toss 인증 페이지로 리다이렉트 — 성공 시 /billing/success 로 복귀.
      await requestCardBillingAuth(config.client_key, config.customer_key);
    } catch {
      setError("결제 위젯을 여는 중 오류가 발생했습니다.");
      setBusy(false);
    }
  }

  const plan = config?.plan ?? sub?.plan;
  const status = sub?.status ?? "none";
  const meta = STATUS_META[status] ?? STATUS_META.none;
  const isActive = status === "active" || status === "trialing";
  const amount = plan ? plan.amount.toLocaleString() : "—";

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-base font-semibold text-ink">플랜 & 결제</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.cls}`}>
          {meta.label}
        </span>
      </div>
      <p className="text-sm text-ink-400 mb-4">
        매일 아침 맞춤 공고 추천 + 카카오 알림톡 발송
      </p>

      <div className="rounded-lg border border-surface-border p-4 mb-4">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="text-sm font-medium text-ink">
              {plan?.name ?? "WaterNature 베이직"}
            </p>
            <p className="text-xs text-ink-400 mt-0.5">월 구독 · 부가세 별도</p>
          </div>
          <p className="text-xl font-bold text-ink">
            ₩{amount}
            <span className="text-sm font-normal text-ink-400">/월</span>
          </p>
        </div>
        {sub?.current_period_end && isActive && (
          <p className="text-xs text-ink-400 mt-2">
            다음 결제일:{" "}
            {new Date(sub.current_period_end).toLocaleDateString("ko-KR")}
          </p>
        )}
        {status === "past_due" && (
          <p className="text-xs text-red-600 dark:text-red-300 mt-2">
            최근 결제가 실패했습니다. 카드를 다시 등록해 주세요.
          </p>
        )}
      </div>

      {config?.mode === "test" && (
        <p className="text-xs text-amber-600 dark:text-amber-300 mb-3">
          ⚠️ 테스트 모드 — 실제 결제가 발생하지 않습니다.
        </p>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-300 mb-3">{error}</p>}

      {isActive ? (
        <Button
          variant="secondary"
          onClick={() => cancelMutation.mutate()}
          loading={cancelMutation.isPending}
        >
          구독 해지
        </Button>
      ) : (
        <Button onClick={handleSubscribe} loading={busy} disabled={isLoading}>
          {status === "canceled" || status === "past_due" ? "다시 구독하기" : "구독하기"}
        </Button>
      )}
    </div>
  );
}
