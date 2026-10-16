"use client";

import { Page } from "@/components/Page";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Empty, Notice, PageTitle, ShieldIcon, Spinner } from "@/components/ui";
import { when } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

function describe(e: AuditEntry): string {
  const d = e.detail as Record<string, string | number | string[] | undefined>;
  switch (e.event_type) {
    case "household.created":
      return `Household "${d.name}" created`;
    case "household.member_invited":
      return `${d.invited_by} invited ${d.email} as ${d.role === "elder" ? "account owner" : "approver"}`;
    case "household.member_joined":
      return `${d.email} joined`;
    case "consent.granted":
      return `Access given to ${d.approver}: ${(d.scopes as string[]).map((s) => s.replace("_", " ")).join(", ")}`;
    case "consent.revoked":
      return `Access removed for ${d.approver}`;
    case "bank.connected":
      return `Bank connected: ${d.institution ?? "bank"}`;
    case "bank.synced":
      return `Bank synced — ${d.added} new transactions, ${d.new_alerts} new alerts`;
    case "alert.raised":
      return `Alert: ${d.title}`;
    case "alert.confirmed_fraud":
      return `${d.by} marked as fraud: ${d.title}${d.blocked_payee ? ` (blocked ${d.blocked_payee})` : ""}`;
    case "alert.confirmed_legit":
      return `${d.by} marked as fine: ${d.title}`;
    case "alert.dismissed":
      return `${d.by} dismissed: ${d.title}`;
    case "bill.recorded":
      return `Bill recorded: ${d.payee} $${d.amount}`;
    case "approval.requested":
      return `Warden asked for approval: ${d.summary ?? ""}`;
    case "approval.approved":
      return `${d.by} approved: ${d.summary}`;
    case "approval.denied":
      return `${d.by} blocked: ${d.summary}`;
    case "approval.expired":
      return `Expired without a decision: ${d.summary}`;
    case "payment.succeeded":
      return `Paid ${d.payee} $${d.amount}${d.livemode ? "" : " (test mode)"} · ${d.stripe_payment_intent}`;
    case "payment.failed":
      return `Payment to ${d.payee} failed: ${d.error}`;
    case "execution.failed":
      return `Couldn't complete an approved action: ${d.error}`;
    case "subscription.cancel_requested":
      return `Cancellation prepared for ${d.merchant}`;
    default:
      return e.event_type;
  }
}

export default function ActivityPage() {
  const { data, loading, error, household } = useHouseholdData<AuditEntry[]>("audit", []);
  if (!household) return null;
  return (
    <Page>
      <PageTitle title="Activity" subtitle="Everything Warden and your family did, in order. Nothing here can be edited or deleted." />
      {loading && <Spinner />}
      {error && <Notice tone="red">{error}</Notice>}
      {!loading && !error && data.length === 0 && <Empty title="Nothing yet" />}
      <ol className="space-y-1">
        {data.map((e) => (
          <li key={e.id} className="flex gap-4 rounded-xl px-3 py-3 hover:bg-white/[0.03]">
            <span className="mt-1 text-white/35">
              {e.agent_id === "warden" ? <ShieldIcon /> : <span className="block h-1.5 w-1.5 translate-y-1.5 rounded-full bg-white/40" />}
            </span>
            <div className="min-w-0">
              <p className="text-white/90">{describe(e)}</p>
              <p className="text-sm text-white/40">
                {when(e.created_at)}
                {e.actor && ` · ${e.actor}`}
                {!e.actor && e.agent_id && ` · ${e.agent_id[0].toUpperCase()}${e.agent_id.slice(1)}`}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </Page>
  );
}
