"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingPage } from "@/components/ui/Spinner";

/** 키워드 워치는 '공고 탐색'의 키워드 워치 탭으로 통합 — 기존 링크/북마크 보존용 리다이렉트. */
export default function WatchRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/opportunities?tab=watch");
  }, [router]);
  return <LoadingPage />;
}
