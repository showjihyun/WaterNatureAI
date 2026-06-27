import { create } from "zustand";

// 토큰의 정본은 lib/api/client.ts(메모리 access 토큰) + httpOnly 쿠키(refresh)다.
// localStorage에는 어떤 토큰도 저장하지 않는다(XSS 탈취 방지). 이 스토어는 access
// 토큰을 구독 가능한 형태로 노출하고 싶을 때만 쓰는 얇은 메모리 래퍼.
interface AuthState {
  accessToken: string | null;
  setAccessToken: (token: string | null) => void;
  clearAccessToken: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setAccessToken: (token) => set({ accessToken: token }),
  clearAccessToken: () => set({ accessToken: null }),
}));
