// Static mirror of apps/api/app/agents/definitions.py, for first paint
// before the frontend fetches GET /agents from the live API.
// Keep names/roles in sync manually until that wiring lands (Fase 1).

export type AgentSummary = {
  id: string;
  name: string;
  role: string;
};

export const AGENTS: AgentSummary[] = [
  { id: "milo", name: "Milo", role: "Coordinator — orchestrates and delegates across the fleet" },
  { id: "scout", name: "Scout", role: "Research, web browsing, computer use" },
  { id: "herald", name: "Herald", role: "Email and messages (always asks before sending)" },
  { id: "ledger", name: "Ledger", role: "Numbers, analysis, code sandbox" },
  { id: "scribe", name: "Scribe", role: "Documents and retrieval" },
  { id: "courier", name: "Courier", role: "Files" },
  { id: "warden", name: "Warden", role: "Approvals, credential vault, purchase gate" },
  { id: "sentinel", name: "Sentinel", role: "Background monitoring and alerts" },
];
