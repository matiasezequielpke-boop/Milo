// Shapes returned by apps/api (see app/schemas.py). Amounts arrive as
// strings (Decimal) and are formatted, never re-computed, on this side.

export type Role = "elder" | "approver";
export type Scope = "view_accounts" | "receive_alerts" | "approve_actions";

export type Member = {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  status: "invited" | "active" | "removed";
  is_me: boolean;
  scopes: Scope[];
};

export type Consent = {
  id: string;
  approver_member_id: string;
  scopes: Scope[];
  text_version: string;
  granted_at: string;
  revoked_at: string | null;
};

export type Household = {
  id: string;
  name: string;
  my_member_id: string;
  my_role: Role;
  my_scopes: Scope[];
  members: Member[];
  consents: Consent[];
  created_at: string;
};

export type InviteResult = {
  member: Member;
  invite_link: string | null;
  emailed: boolean;
};

export type Integrations = {
  model: boolean;
  model_id: string;
  plaid: boolean;
  plaid_env: string;
  stripe: boolean;
  stripe_mode: "test" | "live" | null;
  email: boolean;
  push: boolean;
  dev_auth: boolean;
};

export type Approval = {
  id: string;
  household_id: string | null;
  conversation_id: string | null;
  agent_id: string;
  action_type: string;
  payload: Record<string, unknown>;
  summary: string | null;
  status: "pending" | "approved" | "denied" | "expired";
  requested_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
  execution_result: Record<string, unknown> | null;
  can_resolve: boolean;
};

export type Transaction = {
  id: string;
  account_id: string;
  amount: string;
  currency: string;
  date: string;
  name: string;
  merchant_name: string | null;
  category: string | null;
  pending: boolean;
};

export type Alert = {
  id: string;
  kind: string;
  severity: "low" | "medium" | "high";
  title: string;
  reasons: string[];
  status: "open" | "confirmed_legit" | "confirmed_fraud" | "dismissed";
  transaction: Transaction | null;
  created_at: string;
  resolved_at: string | null;
};

export type Account = {
  id: string;
  name: string;
  mask: string | null;
  type: string | null;
  subtype: string | null;
  current_balance: string | null;
  available_balance: string | null;
  currency: string;
  institution_name: string | null;
};

export type Subscription = {
  id: string;
  merchant_name: string;
  kind: "subscription" | "bill";
  average_amount: string;
  last_amount: string;
  cadence_days: number;
  charge_count: number;
  last_charged_on: string;
  status: string;
};

export type Bill = {
  id: string;
  payee_name: string;
  payee_blocked: boolean;
  amount: string;
  currency: string;
  due_date: string | null;
  reference: string | null;
  status: string;
  created_at: string;
};

export type AuditEntry = {
  id: number;
  event_type: string;
  agent_id: string | null;
  actor: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export type Conversation = {
  id: string;
  household_id: string | null;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "agent" | "system";
  agent_id: string | null;
  content: string;
  created_at: string;
};

export type SyncResult = {
  connections: number;
  accounts: number;
  added: number;
  modified: number;
  removed: number;
  new_alerts: number;
};
