import { apiFetch } from "./client";

export interface BillingPlan {
  code: string;
  name: string;
  amount: number;
  interval: string;
}

export interface BillingConfig {
  provider: string;
  client_key: string;
  mode: string;
  customer_key: string;
  plan: BillingPlan;
}

export interface SubscriptionState {
  status: string; // none | trialing | active | past_due | canceled
  plan_code: string | null;
  current_period_end: string | null;
  canceled_at?: string | null;
  plan: BillingPlan;
}

export function getBillingConfig() {
  return apiFetch<BillingConfig>("/billing/config");
}

export function getSubscription() {
  return apiFetch<SubscriptionState>("/billing/subscription");
}

export function subscribe(authKey: string, customerKey: string) {
  return apiFetch<SubscriptionState>("/billing/subscribe", {
    method: "POST",
    body: JSON.stringify({ auth_key: authKey, customer_key: customerKey }),
  });
}

export function cancelSubscription() {
  return apiFetch<SubscriptionState>("/billing/cancel", { method: "POST" });
}
