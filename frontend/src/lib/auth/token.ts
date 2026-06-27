// ────────────────────────────────────────────────────────────────────────────
// JWT token utilities — no external dependencies
// ────────────────────────────────────────────────────────────────────────────

const ACCESS_KEY = "bizradar_access_token";

/**
 * Decodes the JWT payload from the access token in localStorage and checks
 * whether it is present and not expired.
 *
 * Returns false when:
 *  - running on the server (SSR)
 *  - no token in localStorage
 *  - token cannot be parsed (malformed)
 *  - payload.exp is missing or has already elapsed
 */
export function isAccessTokenValid(): boolean {
  if (typeof window === "undefined") return false;

  const token = localStorage.getItem(ACCESS_KEY);
  if (!token) return false;

  try {
    // A JWT has three base64url-encoded segments separated by '.'
    const parts = token.split(".");
    if (parts.length !== 3) return false;

    // Pad the base64url segment to a multiple of 4 before decoding
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const payload = JSON.parse(atob(padded)) as Record<string, unknown>;

    if (typeof payload.exp !== "number") return false;

    // exp is in seconds; Date.now() is in milliseconds
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}
