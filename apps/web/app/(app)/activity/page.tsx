"use client";

import { useEffect } from "react";

import { Toy } from "@/components/Toy";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Empty, Notice, Ready, Spinner } from "@/components/ui";
import { when } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { AgentSchedule, AuditEntry } from "@/lib/types";

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
    case "agent.created":
      return `${d.by} made the agent "${d.name}" · ${RUNS[d.schedule as AgentSchedule] ?? "runs when asked"}`;
    case "agent.updated":
      return `${d.by} changed the agent "${d.name}"`;
    case "agent.deleted":
      return `${d.by} deleted the agent "${d.name}"`;
    default:
      return e.event_type;
  }
}

const RUNS: Record<AgentSchedule, string> = {
  manual: "runs when asked",
  weekly: "runs every Monday",
  monthly: "runs on the 1st of each month",
};

const AGENT_TOY = { warden: "lock", sentinel: "star", milo: "beacon" } as const;

function Activity() {
  const { data, loading, error, household } = useHouseholdData<AuditEntry[]>("audit", []);
  if (!household) return null;
  return (
    <>
      <p className="lede">Everything Warden and the family did, in order. Nothing here can be edited or deleted.</p>
      {loading && <Spinner />}
      {error && <Notice tone="err">{error}</Notice>}
      {!loading && !error && data.length === 0 && <Empty title="Nothing yet" />}
      {data.length > 0 && (
        <ol className="tl card glass">
          {data.map((e) => {
            const kind = e.agent_id ? AGENT_TOY[e.agent_id as keyof typeof AGENT_TOY] : undefined;
            return (
              <li key={e.id}>
                <span className="ic">{kind ? <Toy kind={kind} /> : <i />}</span>
                <div>
                  <p>{describe(e)}</p>
                  <span>
                    {when(e.created_at)}
                    {e.actor && ` · ${e.actor}`}
                    {!e.actor && e.agent_id && ` · ${e.agent_id[0].toUpperCase()}${e.agent_id.slice(1)}`}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}

export default function ActivityPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  useEffect(() => setCrumb("Activity"), [setCrumb]);
  return (
    <div className="panel">
      <Ready>
        <Activity />
      </Ready>
    </div>
  );
}
