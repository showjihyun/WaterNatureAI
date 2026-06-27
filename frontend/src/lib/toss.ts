// ────────────────────────────────────────────────────────────────────────────
// Toss Payments SDK loader — 자동결제(빌링) 카드 등록 플로우.
// v1 스크립트를 동적 주입 → window.TossPayments(clientKey).requestBillingAuth.
// requestBillingAuth 는 Toss 인증 페이지로 리다이렉트하며, 성공 시 successUrl 로
// authKey/customerKey 쿼리와 함께 돌아온다. (테스트 키는 사업자등록 불필요.)
// ────────────────────────────────────────────────────────────────────────────

interface TossPaymentsInstance {
  requestBillingAuth(
    method: string,
    options: { customerKey: string; successUrl: string; failUrl: string }
  ): Promise<void>;
}

declare global {
  interface Window {
    TossPayments?: (clientKey: string) => TossPaymentsInstance;
  }
}

const SDK_SRC = "https://js.tosspayments.com/v1/payment";
let loadingPromise: Promise<void> | null = null;

function ensureScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("브라우저 환경이 아닙니다."));
  if (window.TossPayments) return Promise.resolve();
  if (loadingPromise) return loadingPromise;
  loadingPromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SDK_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loadingPromise = null;
      reject(new Error("Toss SDK 로드 실패"));
    };
    document.head.appendChild(s);
  });
  return loadingPromise;
}

/** 카드 등록(빌링 인증) 요청 → Toss 인증 페이지로 리다이렉트. */
export async function requestCardBillingAuth(
  clientKey: string,
  customerKey: string
): Promise<void> {
  await ensureScript();
  if (!window.TossPayments) throw new Error("Toss SDK 초기화 실패");
  const tossPayments = window.TossPayments(clientKey);
  const origin = window.location.origin;
  await tossPayments.requestBillingAuth("카드", {
    customerKey,
    successUrl: `${origin}/billing/success`,
    failUrl: `${origin}/billing/fail`,
  });
}
