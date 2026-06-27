// ────────────────────────────────────────────────────────────────────────────
// API client — access token in memory (+ Authorization header); the refresh
// token lives in an httpOnly cookie set by the backend, so JS never sees it.
// On 401 (incl. fresh page loads where the in-memory token is gone) we silently
// re-mint the access token from the refresh cookie.
// ────────────────────────────────────────────────────────────────────────────

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

// Access token kept in memory ONLY (not localStorage) → not stealable via XSS,
// short-lived, and re-minted from the httpOnly refresh cookie after a reload.
let accessToken: string | null = null;

function getToken(): string | null {
  return accessToken;
}

function setToken(access: string) {
  accessToken = access;
}

function clearToken() {
  accessToken = null;
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  try {
    // No body — the refresh token rides along as the httpOnly cookie.
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      clearToken();
      return false;
    }
    const data = await res.json();
    setToken(data.access_token);
    return true;
  } catch {
    clearToken();
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

  // credentials:'include' so the httpOnly refresh cookie is set on login/register
  // and sent on /auth/* calls. The cookie path is scoped to /auth, so it is not
  // attached to ordinary API calls.
  let res = await fetch(url, { ...options, headers, credentials: "include" });

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
      res = await fetch(url, { ...options, headers, credentials: "include" });
    }
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = undefined;
    }

    // 401 confirmed (refresh failed/skipped): clear token and redirect to /login —
    // but only for non-auth endpoints so the login page shows its own error and
    // we avoid redirect loops.
    if (
      res.status === 401 &&
      !path.startsWith("/auth/") &&
      typeof window !== "undefined"
    ) {
      clearToken();
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

  let res = await fetch(url, {
    method: "POST",
    headers: buildHeaders(),
    body: formData,
    credentials: "include",
  });

  if (res.status === 401) {
    if (!refreshing) {
      refreshing = tryRefresh().finally(() => {
        refreshing = null;
      });
    }
    const ok = await refreshing;
    if (ok) {
      res = await fetch(url, {
        method: "POST",
        headers: buildHeaders(),
        body: formData,
        credentials: "include",
      });
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

export { setToken, clearToken, getToken, tryRefresh };
