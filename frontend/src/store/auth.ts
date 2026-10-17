import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Profile } from "@/types/api";

interface AuthState {
  token: string | null;
  profile: Profile | null;
  setSession: (token: string, profile: Profile) => void;
  setProfile: (profile: Profile) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      profile: null,
      setSession: (token, profile) => set({ token, profile }),
      setProfile: (profile) => set({ profile }),
      logout: () => set({ token: null, profile: null }),
    }),
    { name: "aigc-hub.auth" },
  ),
);

interface UiState {
  dark: boolean;
  collapsed: boolean;
  toggleDark: () => void;
  setCollapsed: (v: boolean) => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      dark: false,
      collapsed: false,
      toggleDark: () => set((s) => ({ dark: !s.dark })),
      setCollapsed: (collapsed) => set({ collapsed }),
    }),
    { name: "aigc-hub.ui" },
  ),
);
