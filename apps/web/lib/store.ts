"use client";

import { create } from "zustand";

import type { ToyKind } from "@/components/Toy";
import { api, API_URL, ApiError } from "@/lib/api";
import { getDemoEmail, setDemoEmail } from "@/lib/auth";
import type { Alert, Approval, Conversation, DemoBootstrap, DemoPerson, Household, Integrations, Me } from "@/lib/types";

// offline     — this site has no API configured (NEXT_PUBLIC_API_URL unset)
// unreachable — an API is configured but didn't answer
// no-demo     — the API answered but isn't running in DEMO_MODE, and
//               sign-in is switched off in this build
export type Status = "loading" | "offline" | "unreachable" | "no-demo" | "ready";

type Toast = { id: number; text: string; kind: ToyKind };

type State = {
  status: Status;
  error: string | null;
  people: DemoPerson[];
  me: Me | null;
  households: Household[];
  activeId: string | null;
  integrations: Integrations | null;
  pendingApprovals: number;
  openAlerts: number;
  conversations: Conversation[];
  activeConversation: string | null;
  crumb: { title: string; sub?: string };
  toast: Toast | null;
  sheet: string | null;
  load: () => Promise<void>;
  switchPerson: (email: string) => Promise<void>;
  refreshHouseholds: () => Promise<void>;
  refreshCounts: () => Promise<void>;
  refreshConversations: () => Promise<void>;
  setConversation: (id: string | null) => void;
  setCrumb: (title: string, sub?: string) => void;
  showToast: (text: string, kind?: ToyKind) => void;
  openSheet: (agentId: string | null) => void;
};

let toastSeq = 0;

export const useApp = create<State>((set, get) => {
  // Everything that depends on who is viewing: who they are, their
  // household, their chats and the badge counts.
  async function enter() {
    const me = await api<Me>("/auth/me");
    const households = await api<Household[]>("/households");
    set({ me, households, activeId: households[0]?.id ?? null });
    await Promise.all([get().refreshCounts(), get().refreshConversations()]);
    set({ status: "ready", error: null });
  }

  return {
    status: "loading",
    error: null,
    people: [],
    me: null,
    households: [],
    activeId: null,
    integrations: null,
    pendingApprovals: 0,
    openAlerts: 0,
    conversations: [],
    activeConversation: null,
    crumb: { title: "New task" },
    toast: null,
    sheet: null,

    load: async () => {
      if (!API_URL) {
        set({ status: "offline" });
        return;
      }
      try {
        const integrations = await api<Integrations>("/integrations");
        set({ integrations });
        if (!integrations.demo_mode) {
          set({ status: "no-demo" });
          return;
        }
        const boot = await api<DemoBootstrap>("/demo/bootstrap", { method: "POST" });
        const saved = getDemoEmail();
        const person = boot.people.find((p) => p.email === saved) ?? boot.people[0];
        setDemoEmail(person.email);
        set({ people: boot.people });
        await enter();
      } catch (e) {
        set({ status: "unreachable", error: e instanceof ApiError || e instanceof Error ? e.message : null });
      }
    },

    switchPerson: async (email) => {
      const person = get().people.find((p) => p.email === email);
      if (!person || email === get().me?.email) return;
      setDemoEmail(email);
      set({ activeConversation: null, conversations: [], pendingApprovals: 0, openAlerts: 0 });
      try {
        await enter();
        get().showToast(`Now viewing as ${person.name}`, person.role === "elder" ? "beacon" : "lock");
      } catch (e) {
        set({ status: "unreachable", error: e instanceof Error ? e.message : null });
      }
    },

    refreshHouseholds: async () => {
      const households = await api<Household[]>("/households");
      const activeId = households.some((h) => h.id === get().activeId) ? get().activeId : households[0]?.id ?? null;
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

    refreshConversations: async () => {
      const id = get().activeId;
      if (!id) return;
      const conversations = await api<Conversation[]>(`/conversations?household_id=${id}`).catch(() => [] as Conversation[]);
      set({ conversations });
    },

    setConversation: (id) => set({ activeConversation: id }),
    setCrumb: (title, sub) => set({ crumb: { title, sub } }),
    showToast: (text, kind = "beacon") => set({ toast: { id: ++toastSeq, text, kind } }),
    openSheet: (agentId) => set({ sheet: agentId }),
  };
});

export function useActiveHousehold(): Household | null {
  return useApp((s) => s.households.find((h) => h.id === s.activeId) ?? null);
}
