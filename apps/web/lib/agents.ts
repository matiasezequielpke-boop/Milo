import type { ToyKind } from "@/components/Toy";

// The cast. Only Milo, Warden and Sentinel exist in this build; the rest
// are shown as "coming soon" and never answer or claim to do anything.
export type CastAgent = {
  id: string;
  name: string;
  role: string;
  kind: ToyKind;
  live: boolean;
  about: string;
  does: string[];
};

export const CAST: CastAgent[] = [
  {
    id: "milo",
    name: "Milo",
    role: "Talks with you",
    kind: "beacon",
    live: true,
    about:
      "The one you chat with. Milo reads the real accounts, bills and alerts to answer, and hands anything that pays or cancels to Warden.",
    does: [
      "Answers from the connected accounts, not from a script",
      "Explains charges, bills and recurring payments",
      "Asks Warden when something needs paying or cancelling",
      "Replies in the language you write in",
    ],
  },
  {
    id: "warden",
    name: "Warden",
    role: "Approvals & payments",
    kind: "lock",
    live: true,
    about:
      "The only agent that can move money, and it never acts alone. Every payment or cancellation waits for a family approver's yes, and every step is logged.",
    does: [
      "Holds every payment until a family approver says yes",
      "Pays exactly what was approved, nothing else",
      "Refuses to pay anyone the family marked as fraud",
      "Writes every request and decision to the activity log",
    ],
  },
  {
    id: "sentinel",
    name: "Sentinel",
    role: "Scam & charge alerts",
    kind: "star",
    live: true,
    about:
      "Checks every new charge after a bank sync and speaks up only when something looks wrong, with the reasons spelled out.",
    does: [
      "Flags gift cards, crypto, wires and big payments to someone new",
      "Spots duplicates, unusual amounts and price jumps",
      "Finds new subscriptions and tells bills apart from them",
      "Lets the family mark a charge as fine or as fraud",
    ],
  },
  {
    id: "scout",
    name: "Scout",
    role: "Research & compare",
    kind: "lens",
    live: false,
    about: "Will compare rates, providers and plans, and find a better deal on what's already being paid.",
    does: ["Compare rates and providers", "Bring the source for every claim"],
  },
  {
    id: "herald",
    name: "Herald",
    role: "Calls & messages",
    kind: "envelope",
    live: false,
    about: "Will contact companies for you — cancel, negotiate, chase support — and only after your yes.",
    does: ["Draft cancellation and negotiation requests", "Send only after approval"],
  },
  {
    id: "ledger",
    name: "Ledger",
    role: "Spending & budgets",
    kind: "calc",
    live: false,
    about: "Will track spending and budgets, and show the working behind every number.",
    does: ["Monthly spending summaries", "Price-creep and outlier reports"],
  },
  {
    id: "scribe",
    name: "Scribe",
    role: "Letters & documents",
    kind: "paper",
    live: false,
    about: "Will draft letters and summaries from statements, policies and receipts.",
    does: ["Draft letters in your tone", "Summarize long documents"],
  },
  {
    id: "courier",
    name: "Courier",
    role: "Receipts & files",
    kind: "parcel",
    live: false,
    about: "Will file receipts and statements where they belong.",
    does: ["File receipts and statements", "Never delete without asking"],
  },
];

export const agentById = (id: string | null | undefined): CastAgent => CAST.find((a) => a.id === id) ?? CAST[0];
