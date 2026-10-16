"use client";

import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import type { Approval, Alert, Household, Integrations } from "@/lib/types";

type Me = { id: string; email: string; display_name: string | null };

type State = {
  status: "loading" | "signed-out" | "ready";
  me: Me | null;
  households: Household[];
  activeId: string | null;
  integrations: Integrations | null;
  pendingApprovals: number;
  openAlerts: number;
  error: string | null;
  load: () => Promise<void>;
  refreshHouseholds: () => Promise<void>;
  refreshCounts: () => Promise<void>;
  setActive: (id: string) => void;
};

const ACTIVE_KEY = "warden.activeHousehold";

export const useApp = create<State>((set, get) => ({
  status: "loading",
  me: null,
  households: [],
  activeId: null,
  integrations: null,
  pendingApprovals: 0,
  openAlerts: 0,
  error: null,

  load: async () => {
    try {
      const [me, integrations] = await Promise.all([
        api<Me>("/auth/me"),
        api<Integrations>("/integrations").catch(() => null),
      ]);
      set({ me, integrations, error: null });
      // Households first, then "ready": the shell redirects to onboarding
      // when a ready user has none, so ready must never precede them.
      await get().refreshHouseholds();
      set({ status: "ready" });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) set({ status: "signed-out", me: null });
      else set({ status: "signed-out", error: e instanceof Error ? e.message : "Can't reach Warden." });
    }
  },

  refreshHouseholds: async () => {
    const households = await api<Household[]>("/households");
    let activeId = get().activeId;
    if (!activeId) {
      try {
        activeId = window.localStorage.getItem(ACTIVE_KEY);
      } catch {
        activeId = null;
      }
    }
    if (!households.some((h) => h.id === activeId)) activeId = households[0]?.id ?? null;
    set({ households, activeId });
    await get().refreshCounts();
  },

  refreshCounts: async () => {
    const h = get().households.find((x) => x.id === get().activeId);
    if (!h || !h.my_scopes.includes("view_accounts")) {
      set({ pendingApprovals: 0, openAlerts: 0 });
      return;
    }
    const [approvals, alerts] = await Promise.all([
      api<Approval[]>(`/approvals?household_id=${h.id}&status_filter=pending`).catch(() => []),
      api<Alert[]>(`/households/${h.id}/alerts`).catch(() => []),
    ]);
    set({ pendingApprovals: approvals.length, openAlerts: alerts.length });
  },

  setActive: (id) => {
    try {
      window.localStorage.setItem(ACTIVE_KEY, id);
    } catch {
      /* not persisted; fine */
    }
    set({ activeId: id });
    void get().refreshCounts();
  },
}));

export function useActiveHousehold(): Household | null {
  return useApp((s) => s.households.find((h) => h.id === s.activeId) ?? null);
}
