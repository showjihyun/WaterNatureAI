"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { LoadingPage } from "@/components/ui/Spinner";
import { isAccessTokenValid } from "@/lib/auth/token";
import { tryRefresh } from "@/lib/api/client";

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  // access 토큰은 메모리에만 있어 새로고침 시 사라진다. 마운트 시 httpOnly 리프레시
  // 쿠키로 silent refresh를 시도해 access를 복구한 뒤 인증 여부를 판단한다(쿠키 없으면 실패).
  const [status, setStatus] = useState<"loading" | "ok" | "denied">("loading");

  useEffect(() => {
    let alive = true;
    (async () => {
      const ok = isAccessTokenValid() || (await tryRefresh());
      if (alive) setStatus(ok ? "ok" : "denied");
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (status === "denied") router.replace("/login");
  }, [status, router]);

  // 인증 확인/리다이렉트 중 → 로딩. children을 렌더하지 않아 죽은 토큰으로 API 호출 방지.
  if (status !== "ok") return <LoadingPage />;

  return <>{children}</>;
}
