"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { LoadingPage } from "@/components/ui/Spinner";
import { isAccessTokenValid } from "@/lib/auth/token";
import { clearTokens } from "@/lib/api/client";

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  // localStorage(토큰)는 서버에 없으므로 렌더 중 직접 분기하면 SSR↔클라이언트 hydration
  // mismatch가 난다. mount 이후에만 토큰을 검사(서버·첫 클라이언트 렌더는 동일하게 로딩).
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const tokenValid = mounted && isAccessTokenValid();

  useEffect(() => {
    if (mounted && !tokenValid) {
      clearTokens();
      router.replace("/login");
    }
  }, [mounted, tokenValid, router]);

  // mount 전(=서버/첫 렌더) 또는 토큰 무효(리다이렉트 중) → 로딩.
  // children을 렌더하지 않아 죽은 토큰으로 401 API 호출하는 것을 방지.
  if (!mounted || !tokenValid) {
    return <LoadingPage />;
  }

  return <>{children}</>;
}
