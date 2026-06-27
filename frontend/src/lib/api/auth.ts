import { apiFetch, setTokens, clearTokens } from "./client";
import type { TokenOut, LoginIn, RegisterIn } from "@/types/api";

export async function register(body: RegisterIn): Promise<TokenOut> {
  const data = await apiFetch<TokenOut>("/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function login(body: LoginIn): Promise<TokenOut> {
  const data = await apiFetch<TokenOut>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function logout(refreshToken: string): Promise<void> {
  try {
    await apiFetch("/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } finally {
    clearTokens();
  }
}
