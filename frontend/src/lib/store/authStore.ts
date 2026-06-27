import { create } from "zustand";

const ACCESS_KEY = "bizradar_access_token";
const REFRESH_KEY = "bizradar_refresh_token";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (access: string, refresh: string) => void;
  clearTokens: () => void;
  getAccessToken: () => string | null;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken:
    typeof window !== "undefined" ? localStorage.getItem(ACCESS_KEY) : null,
  refreshToken:
    typeof window !== "undefined" ? localStorage.getItem(REFRESH_KEY) : null,

  setTokens: (access: string, refresh: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(ACCESS_KEY, access);
      localStorage.setItem(REFRESH_KEY, refresh);
    }
    set({ accessToken: access, refreshToken: refresh });
  },

  clearTokens: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    }
    set({ accessToken: null, refreshToken: null });
  },

  getAccessToken: () => {
    if (typeof window !== "undefined") {
      return localStorage.getItem(ACCESS_KEY);
    }
    return get().accessToken;
  },
}));
