import { apiFetch, setToken, clearToken } from "./client";
import type { TokenOut, LoginIn, RegisterIn } from "@/types/api";

export async function register(body: RegisterIn): Promise<TokenOut> {
  const data = await apiFetch<TokenOut>("/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
  setToken(data.access_token); // refresh 토큰은 httpOnly 쿠키로 자동 저장됨
  return data;
}

export async function login(body: LoginIn): Promise<TokenOut> {
  const data = await apiFetch<TokenOut>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  setToken(data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    // 본문 없음 — 서버가 httpOnly 리프레시 쿠키를 읽어 폐기·삭제한다.
    await apiFetch("/auth/logout", { method: "POST" });
  } finally {
    clearToken();
  }
}
