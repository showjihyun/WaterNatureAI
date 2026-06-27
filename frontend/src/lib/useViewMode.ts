"use client";

import { useCallback, useEffect, useState } from "react";

export type ViewMode = "card" | "list";

const STORAGE_KEY = "bizradar_view_mode";

function isViewMode(value: string | null): value is ViewMode {
  return value === "card" || value === "list";
}

/**
 * Shared list/card view-mode preference.
 *
 * - Persisted to localStorage under a single key so every list-style menu
 *   (dashboard, opportunities) stays in sync.
 * - SSR-safe: the first render is always "card"; the stored value is restored
 *   in an effect to avoid hydration mismatches.
 */
export function useViewMode(): {
  mode: ViewMode;
  setMode: (mode: ViewMode) => void;
} {
  const [mode, setModeState] = useState<ViewMode>("card");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isViewMode(stored)) {
      setModeState(stored);
    }
  }, []);

  const setMode = useCallback((next: ViewMode) => {
    setModeState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  return { mode, setMode };
}
