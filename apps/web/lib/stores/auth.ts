"use client";

import { create } from "zustand";

import { clearToken, getToken, setToken as persistToken, subscribeAuth } from "../auth";

type AuthState = {
  token: string | null;
  setAccessToken: (token: string) => void;
  signOut: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  setAccessToken: (token) => {
    persistToken(token);
    set({ token });
  },
  signOut: () => {
    clearToken();
    set({ token: null });
  },
}));

export const selectToken = (s: AuthState) => s.token;

if (typeof window !== "undefined") {
  useAuthStore.setState({ token: getToken() });
  subscribeAuth(() => useAuthStore.setState({ token: getToken() }));
}
