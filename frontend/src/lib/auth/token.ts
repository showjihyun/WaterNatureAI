// ────────────────────────────────────────────────────────────────────────────
// JWT token utilities — reads the in-memory access token from the API client
// (no localStorage). Refresh is handled separately via the httpOnly cookie.
// ────────────────────────────────────────────────────────────────────────────

import { getToken } from "@/lib/api/client";

/**
 * Returns true when an in-memory access token is present and not expired.
 *
 * Returns false when: no token in memory (e.g. right after a reload, before a
 * silent refresh), the token is malformed, or `payload.exp` has elapsed.
 */
export function isAccessTokenValid(): boolean {
  const token = getToken();
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
