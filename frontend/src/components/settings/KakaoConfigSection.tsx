"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { getKakaoConfig, updateKakaoConfig } from "@/lib/api/settings";
import { ApiError } from "@/lib/api/client";

/**
 * 카카오/SOLAPI 발신 설정 카드 — 시스템 전역(운영자 전용).
 * API 키/시크릿은 입력 시 서버에서 암호화되어 DB에 저장되고 화면에 다시 노출되지 않는다.
 * 비운영자(403)에게는 안내만 표시한다.
 */
export function KakaoConfigSection() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings", "kakao"],
    queryFn: getKakaoConfig,
    retry: false,
  });

  const [senderKey, setSenderKey] = useState("");
  const [templateCode, setTemplateCode] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) {
      setSenderKey(data.sender_key || "");
      setTemplateCode(data.template_briefing || "");
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: updateKakaoConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "kakao"] });
      queryClient.invalidateQueries({ queryKey: ["notification", "preview"] });
      setApiKey("");
      setApiSecret("");
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  // 운영자 전용 — 비운영자/ADMIN_EMAILS 미설정(403)이면 안내만 노출(페이지를 막지 않음).
  if (error instanceof ApiError && error.status === 403) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 mb-1">카카오 발신 설정 (SOLAPI)</h2>
        <p className="text-sm text-gray-500">
          카카오 알림톡 발신 자격증명은 <span className="font-medium text-gray-600">운영자 전용</span>입니다.
          백엔드 <code className="rounded bg-surface px-1 text-xs">ADMIN_EMAILS</code>에 운영자 이메일을 등록하면 여기서 설정할 수 있습니다.
        </p>
      </div>
    );
  }
  if (isLoading) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate({
      sender_key: senderKey.trim() || undefined,
      template_briefing: templateCode.trim() || undefined,
      api_key: apiKey.trim() || undefined,
      api_secret: apiSecret.trim() || undefined,
    });
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900 mb-1">카카오 발신 설정 (SOLAPI)</h2>
      <p className="text-sm text-gray-500 mb-5">
        카카오 알림톡 발송에 쓸 SOLAPI 자격증명과 발신프로필·템플릿을 입력합니다. API 키·시크릿은
        <span className="mx-1 font-medium text-gray-600">암호화되어 DB에 저장</span>되며 화면에 다시 노출되지 않습니다.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label htmlFor="kakao-pfid" className="block text-sm font-medium text-gray-700 mb-1.5">
            발신프로필 키 (pfId)
          </label>
          <input
            id="kakao-pfid"
            type="text"
            value={senderKey}
            onChange={(e) => setSenderKey(e.target.value)}
            placeholder="SOLAPI 발신프로필 pfId"
            autoComplete="off"
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        <div>
          <label htmlFor="kakao-template" className="block text-sm font-medium text-gray-700 mb-1.5">
            알림톡 템플릿 코드 (브리핑)
          </label>
          <input
            id="kakao-template"
            type="text"
            value={templateCode}
            onChange={(e) => setTemplateCode(e.target.value)}
            placeholder="승인된 브리핑 템플릿 코드"
            autoComplete="off"
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        <div>
          <label htmlFor="kakao-apikey" className="block text-sm font-medium text-gray-700 mb-1.5">
            SOLAPI API Key
            {data?.api_key_configured && (
              <span className="ml-2 text-xs font-normal text-emerald-600">✓ 설정됨</span>
            )}
          </label>
          <input
            id="kakao-apikey"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={data?.api_key_configured ? "변경하려면 새 키 입력 (비우면 현재 키 유지)" : "API Key 입력"}
            autoComplete="off"
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        <div>
          <label htmlFor="kakao-apisecret" className="block text-sm font-medium text-gray-700 mb-1.5">
            SOLAPI API Secret
            {data?.api_secret_configured && (
              <span className="ml-2 text-xs font-normal text-emerald-600">✓ 설정됨</span>
            )}
          </label>
          <input
            id="kakao-apisecret"
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder={data?.api_secret_configured ? "변경하려면 새 시크릿 입력 (비우면 현재 값 유지)" : "API Secret 입력"}
            autoComplete="off"
            className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
          <p className="mt-1.5 text-xs text-gray-500">
            입력한 키/시크릿은 서버에서 <span className="text-gray-600">암호화되어 DB에 저장</span>되며,
            저장 후 화면에 다시 표시되지 않습니다.
          </p>
        </div>

        {mutation.isError && <Alert variant="error">저장 실패 — 입력 값을 확인하세요.</Alert>}

        <div className="flex items-center gap-3">
          <Button type="submit" loading={mutation.isPending}>
            저장
          </Button>
          {data?.configured && !saved && (
            <span className="text-xs font-medium text-emerald-600">발송 설정 완료</span>
          )}
          {saved && (
            <span className="text-sm text-emerald-600 font-medium flex items-center gap-1.5">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              저장되었습니다
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
