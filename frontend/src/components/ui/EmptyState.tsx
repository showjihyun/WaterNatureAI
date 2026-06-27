import type { ReactNode } from "react";
import { Button } from "./Button";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-surface-border bg-surface px-6 py-16 text-center">
      {icon && (
        <div className="mb-4 text-ink-400">{icon}</div>
      )}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-ink-400 max-w-sm">{description}</p>
      )}
      {action && (
        <div className="mt-5">
          <Button onClick={action.onClick} variant="secondary" size="sm">
            {action.label}
          </Button>
        </div>
      )}
    </div>
  );
}
