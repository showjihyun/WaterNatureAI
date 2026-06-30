import { cn } from "@/lib/utils";
import { ksicName } from "@/lib/ksic";

/**
 * 표준 업종(KSIC 대분류) 배지 — 코드를 단축명으로 표시.
 * null/ETC(기타)는 렌더하지 않음(노이즈 방지). 메타데이터 톤(중립 surface-muted)으로
 * 키워드 매칭 칩(primary)·수행가능성 배지와 시각적으로 구분.
 */
export function IndustryBadge({
  code,
  className,
}: {
  code: string | null | undefined;
  className?: string;
}) {
  if (!code || code === "ETC") return null;
  const label = ksicName(code, true);
  if (!label) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-medium text-ink-600",
        className
      )}
      title={`업종: ${ksicName(code)}`}
    >
      <svg className="h-2.5 w-2.5 text-ink-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.76V9.75A2.25 2.25 0 0 1 4.5 7.5h15a2.25 2.25 0 0 1 2.25 2.25v3.01M2.25 12.76 12 16.5l9.75-3.74M9 7.5V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v1.5" />
      </svg>
      {label}
    </span>
  );
}
