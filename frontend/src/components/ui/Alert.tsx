import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./Button";

type AlertVariant = "error" | "warning" | "info" | "success";

interface AlertProps {
  variant?: AlertVariant;
  title?: string;
  children?: ReactNode;
  /** 제공 시 우측에 재시도 버튼 노출 — 데이터 재요청(refetch) 등 막다른 에러를 회복 가능하게. */
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

const variantClasses: Record<AlertVariant, string> = {
  error: "border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/15 text-red-700 dark:text-red-300",
  warning: "border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300",
  info: "border-primary-200 bg-primary-50 dark:bg-primary-500/15 text-primary-700 dark:text-primary-300",
  success: "border-emerald-200 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

/** 공용 알림/에러 배너. 페이지마다 재구현하던 border-red-50 div를 대체하고, onRetry로 재시도를 표준화. */
export function Alert({
  variant = "error",
  title,
  children,
  onRetry,
  retryLabel = "다시 시도",
  className,
}: AlertProps) {
  return (
    <div
      role={variant === "error" || variant === "warning" ? "alert" : "status"}
      className={cn(
        "flex items-start justify-between gap-3 rounded-xl border px-4 py-3 text-sm",
        variantClasses[variant],
        className
      )}
    >
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "leading-relaxed")}>{children}</div>}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="shrink-0">
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
