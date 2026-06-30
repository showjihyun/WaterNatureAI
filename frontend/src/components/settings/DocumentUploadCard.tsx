"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiUpload, apiFetch, ApiError } from "@/lib/api/client";

interface UploadResult {
  filename: string;
  page_count: number;
  char_count: number;
}

/**
 * 설정 — 회사소개서(PDF) 업로드/교체. 업로드 후 Company Brain을 재실행해 문서를 반영하고
 * 단일 기업 재매칭을 트리거(온보딩 이후에도 프로필을 보강할 수 있게).
 */
export function DocumentUploadCard({ currentFilename }: { currentFilename?: string | null }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setDone(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiUpload<UploadResult>("/company/documents", fd);
      // 문서 반영 → Brain 재실행(재추출 + 단일 기업 재매칭).
      await apiFetch("/company/brain", { method: "POST" });
      setDone(`'${res.filename}' 반영 완료 — AI가 문서를 읽고 다시 분석하고 있어요.`);
      queryClient.invalidateQueries({ queryKey: ["company", "profile"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations", "today"] });
    } catch (err) {
      const detail =
        err instanceof ApiError && err.detail && typeof err.detail === "object"
          ? (err.detail as { detail?: string }).detail
          : null;
      setError(detail ?? "업로드에 실패했어요. PDF 파일인지 확인해 주세요.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-6 shadow-sm">
      <h2 className="text-base font-semibold text-ink mb-1">회사소개서</h2>
      <p className="text-sm text-ink-400 mb-4">
        회사소개서 PDF를 올리면 AI가 문서를 읽고 역량·실적을 더 정확히 분석해 추천을 갱신합니다.
      </p>

      {currentFilename ? (
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1.5 text-xs text-ink-600">
          <svg className="h-3.5 w-3.5 text-ink-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          현재 파일: <span className="font-medium text-ink">{currentFilename}</span>
        </p>
      ) : (
        <p className="mb-3 text-xs text-ink-400">아직 업로드한 회사소개서가 없습니다.</p>
      )}

      <label
        className={`flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-surface-border px-4 py-3 text-sm font-medium transition-colors hover:border-primary-300 hover:bg-primary-50/40 dark:hover:bg-primary-500/15 ${
          uploading ? "pointer-events-none opacity-60" : "text-ink-600"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={handleFile}
          className="hidden"
          disabled={uploading}
        />
        {uploading ? (
          <>
            <svg className="h-4 w-4 animate-spin text-primary-600 dark:text-primary-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            문서 분석 중…
          </>
        ) : (
          <>
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
            </svg>
            {currentFilename ? "PDF 교체 업로드" : "PDF 파일 선택"}
            <span className="text-xs text-ink-400">· 최대 20MB</span>
          </>
        )}
      </label>

      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-300">{error}</p>}
      {done && <p className="mt-2 text-xs text-green-700 dark:text-green-300">{done}</p>}
    </div>
  );
}
