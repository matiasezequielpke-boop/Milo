import type { ToyKind } from "@/components/Toy";
import type { AgentSchedule, CustomAgent } from "@/lib/types";

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

// ── Agents the family makes ────────────────────────────────────────────
// Each does one job, reads the accounts and reports back. They can't pay,
// cancel or ask for approvals (the API only gives them read-only tools).

export const CUSTOM_PREFIX = "custom:";
export const RUN_NOW_TEXT = "Run your job now and report back.";
// Warden's own agents; the API refuses these names too.
export const RESERVED_NAMES = [...CAST.map((a) => a.id), "warden"];
// Not Milo's, Sentinel's or Warden's faces; the rest are drawn in their
// own colors (Toy `own`), so a family's agent never passes for the cast.
export const CUSTOM_KINDS: ToyKind[] = ["blob", "mug", "stamp", "lens", "envelope", "calc", "paper", "parcel"];

export const SCHEDULES: { value: AgentSchedule; label: string; short: string }[] = [
  { value: "manual", label: "Only when I ask", short: "When you ask" },
  { value: "weekly", label: "Every Monday morning", short: "Every Monday" },
  { value: "monthly", label: "On the 1st of every month", short: "Monthly, on the 1st" },
];
export const scheduleShort = (s: AgentSchedule) => SCHEDULES.find((x) => x.value === s)?.short ?? s;

export const AGENT_TEMPLATES: { name: string; kind: ToyKind; schedule: AgentSchedule; instructions: string }[] = [
  {
    name: "Spending review",
    kind: "calc",
    schedule: "monthly",
    instructions:
      "Review the spending for the past month. Group it by category, compare it with the month before, and point out anything that grew or looks unusual.",
  },
  {
    name: "Bill watch",
    kind: "envelope",
    schedule: "weekly",
    instructions: "List the bills due in the next two weeks with their amounts and due dates, and say if any is higher than usual.",
  },
  {
    name: "Subscription check",
    kind: "parcel",
    schedule: "monthly",
    instructions:
      "List every subscription and recurring charge with what it costs per month and per year. Point out any that started recently or got more expensive.",
  },
  {
    name: "Big charge check",
    kind: "lens",
    schedule: "weekly",
    instructions:
      "Look at the past week's charges and list anything over $200 or from a merchant that hasn't been paid before, with why it stood out.",
  },
];

/** The custom agent a conversation is with, if any. */
export const customRefOf = (participants: string[] | null | undefined): string | null =>
  participants?.length === 1 && participants[0].startsWith(CUSTOM_PREFIX) ? participants[0] : null;

/** Who wrote a message: one of the cast, or an agent the family made
 *  (which may have been deleted since). */
export function speakerFor(id: string | null | undefined, custom: CustomAgent[]): { name: string; kind: ToyKind; own: boolean } {
  if (id?.startsWith(CUSTOM_PREFIX)) {
    const a = custom.find((x) => x.ref === id);
    return a ? { name: a.name, kind: a.kind, own: true } : { name: "Deleted agent", kind: "blob", own: true };
  }
  const a = agentById(id);
  return { name: a.name, kind: a.kind, own: false };
}
