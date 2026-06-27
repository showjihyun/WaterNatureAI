import { cn } from "@/lib/utils";

interface SaveButtonProps {
  saved: boolean;
  onClick: () => void;
  disabled?: boolean;
  /** true면 하트 + 텍스트 라벨(카드용), false면 아이콘 전용(리스트 행용). */
  showLabel?: boolean;
  className?: string;
}

/**
 * 관심(저장) 토글 — Row/Card에서 두 번 손으로 만들던 버튼을 통일.
 * aria-pressed로 상태를 전달(색·텍스트 의존 제거), 용어 통일(관심 등록 / 관심 해제),
 * 터치 타깃 36px(h-9)로 상향.
 */
export function SaveButton({
  saved,
  onClick,
  disabled = false,
  showLabel = false,
  className,
}: SaveButtonProps) {
  const actionLabel = saved ? "관심 해제" : "관심 등록";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={actionLabel}
      aria-pressed={saved}
      title={actionLabel}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary-500 disabled:opacity-50",
        showLabel ? "h-9 px-3 text-sm" : "h-9 w-9",
        saved
          ? "bg-primary-100 text-primary-700 hover:bg-primary-200"
          : "text-ink-400 hover:bg-surface hover:text-ink-600",
        className
      )}
    >
      <svg
        className={cn("h-4 w-4", saved ? "fill-current" : "fill-none stroke-current")}
        viewBox="0 0 24 24"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
      {showLabel && <span>{saved ? "관심 등록됨" : "관심 등록"}</span>}
    </button>
  );
}
