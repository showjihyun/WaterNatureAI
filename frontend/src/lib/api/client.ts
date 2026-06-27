// ────────────────────────────────────────────────────────────────────────────
// API client — auto-attaches Bearer token, handles 401 refresh, mock mode
// ────────────────────────────────────────────────────────────────────────────

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "bizradar_access_token";
const REFRESH_KEY = "bizradar_refresh_token";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

function setTokens(access: string, refresh: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const rt = getRefreshToken();
  if (!rt) {
    // No refresh token — clear any stale access token and bail
    clearTokens();
    return false;
  }
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) {
      clearTokens();
      return false;
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    clearTokens();
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown
  ) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res = await fetch(url, { ...options, headers });

  // 401 → try refresh once
  if (res.status === 401) {
    if (!refreshing) {
      refreshing = tryRefresh().finally(() => {
        refreshing = null;
      });
    }
    const ok = await refreshing;
    if (ok) {
      const newToken = getToken();
      if (newToken) headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(url, { ...options, headers });
    }
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = undefined;
    }

    // 401 confirmed (refresh either failed or was skipped): clear tokens and
    // redirect to /login — but only for non-auth endpoints so that the login
    // page itself can display its own error message and we avoid redirect loops.
    if (
      res.status === 401 &&
      !path.startsWith("/auth/") &&
      typeof window !== "undefined"
    ) {
      clearTokens();
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }

    throw new ApiError(res.status, `HTTP ${res.status}`, detail);
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

/**
 * Multipart upload — like apiFetch but sends FormData. The browser must set
 * `Content-Type: multipart/form-data; boundary=...` itself, so we never set it
 * manually. Reuses the Bearer token + single 401-refresh-retry behavior.
 */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const url = `${API_BASE}${path}`;

  const buildHeaders = (): Record<string, string> => {
    const h: Record<string, string> = {};
    const token = getToken();
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  };

  let res = await fetch(url, { method: "POST", headers: buildHeaders(), body: formData });

  if (res.status === 401) {
    if (!refreshing) {
      refreshing = tryRefresh().finally(() => {
        refreshing = null;
      });
    }
    const ok = await refreshing;
    if (ok) {
      res = await fetch(url, { method: "POST", headers: buildHeaders(), body: formData });
    }
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = undefined;
    }
    throw new ApiError(res.status, `HTTP ${res.status}`, detail);
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export { setTokens, clearTokens, getToken };
