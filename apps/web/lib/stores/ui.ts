"use client";

import { create } from "zustand";

/** UI chrome only — domain lists stay in React Query. */
type UiState = {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
};

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
}));

export const selectSidebarCollapsed = (s: UiState) => s.sidebarCollapsed;
