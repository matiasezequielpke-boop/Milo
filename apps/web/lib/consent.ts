import type { Scope } from "@/lib/types";

// The consent screen's wording. If this changes, bump CONSENT_TEXT_VERSION
// in apps/api/app/households.py so each grant records what was agreed to.
export const SCOPE_TEXT: Record<Scope, { title: string; body: string }> = {
  view_accounts: {
    title: "See my accounts",
    body: "Balances, transactions, bills, and subscriptions. They can't move money just by seeing it.",
  },
  receive_alerts: {
    title: "Get alerts about suspicious charges",
    body: "An email when Warden spots a possible scam or an odd charge, so they can check with me.",
  },
  approve_actions: {
    title: "Approve or block payments and cancellations",
    body: "Warden won't pay a bill or cancel anything without their OK. I'm told every time, and I can block it too.",
  },
};
export const ALL_SCOPES: Scope[] = ["view_accounts", "receive_alerts", "approve_actions"];
