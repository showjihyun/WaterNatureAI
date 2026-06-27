import { cn } from "@/lib/utils";

/**
 * WaterNature 브랜드 마크 — 물방울(라인 아이콘). 색은 currentColor 상속.
 * 기존 레이더 아이콘 5중복을 대체하는 단일 정의.
 */
export function BrandMark({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth="1.5">
      <path
        strokeLinejoin="round"
        d="M12 3.25c0 0 6.75 6.9 6.75 11.4a6.75 6.75 0 11-13.5 0C5.25 10.15 12 3.25 12 3.25z"
      />
      <path strokeLinecap="round" strokeOpacity="0.55" d="M9.4 14.7a2.6 2.6 0 002.1 2.5" />
    </svg>
  );
}

/**
 * 워드마크 — "WaterNature" + 강조 "AI". 다크/라이트 배경 톤만 지정, 크기는 className.
 */
export function Wordmark({
  tone = "light",
  className,
}: {
  tone?: "light" | "dark";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "font-display font-bold tracking-tight",
        tone === "dark" ? "text-white" : "text-ink",
        className
      )}
    >
      WaterNature
      <span className={tone === "dark" ? "text-primary-400" : "text-primary-600"}>AI</span>
    </span>
  );
}

/**
 * 마크 + 워드마크 묶음(로고). 헤더·앱바에서 사용.
 */
export function Brand({
  tone = "light",
  markClassName = "h-5 w-5",
  textClassName = "text-sm",
}: {
  tone?: "light" | "dark";
  markClassName?: string;
  textClassName?: string;
}) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span className={tone === "dark" ? "text-primary-400" : "text-primary-600"}>
        <BrandMark className={markClassName} />
      </span>
      <Wordmark tone={tone} className={textClassName} />
    </span>
  );
}
