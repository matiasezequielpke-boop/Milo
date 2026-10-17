"use client";

import { useState } from "react";

import { Toy } from "@/components/Toy";
import { Chip } from "@/components/ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Approval } from "@/lib/types";

type Result = {
  status?: string;
  stripe_payment_intent?: string;
  livemode?: boolean;
  next_step?: string;
  cancellation_letter?: string;
  error?: string;
} | null;

function statusOf(a: Approval): { label: string; tone?: "ok" | "wait" | "bad" } {
  const r = a.execution_result as Result;
  if (a.status === "approved" && r?.status === "failed") return { label: "Approved — not completed", tone: "bad" };
  if (a.status === "approved" && r?.status === "processing") return { label: "Approved — processing", tone: "wait" };
  return {
    pending: { label: "Waiting for approval", tone: "wait" as const },
    approved: { label: "Approved", tone: "ok" as const },
    denied: { label: "Blocked", tone: "bad" as const },
    expired: { label: "Expired" },
  }[a.status];
}

/** One approval request. In the chat it's a Warden message; on the
 *  Approvals page it's a card. Either way: solid, high contrast, and the
 *  two choices are approve or block — this is the moment money moves. */
export function ApprovalCard({
  approval,
  variant = "card",
  onResolved,
}: {
  approval: Approval;
  variant?: "card" | "bubble";
  onResolved: (a: Approval) => void;
}) {
  const household = useActiveHousehold();
  const people = useApp((s) => s.people);
  const switchPerson = useApp((s) => s.switchPerson);
  const showToast = useApp((s) => s.showToast);
  const [busy, setBusy] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canApprove = Boolean(household?.my_scopes.includes("approve_actions"));
  const p = approval.payload as Record<string, string | null>;
  const r = approval.execution_result as Result;
  const st = statusOf(approval);
  const approver = household?.members.find((m) => m.role === "approver" && m.status === "active");
  const approverPerson = people.find((x) => x.role === "approver");

  async function resolve(kind: "approve" | "deny") {
    setBusy(kind);
    setError(null);
    try {
      const a = await api<Approval>(`/approvals/${approval.id}/${kind}`, { method: "POST", body: {} });
      const res = a.execution_result as Result;
      showToast(
        kind === "deny"
          ? "Blocked. Nothing was done."
          : res?.status === "failed"
            ? "Approved, but it couldn't be completed. No money moved."
            : res?.status === "succeeded"
              ? "Approved and paid."
              : "Approved.",
        "lock",
      );
      onResolved(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't do that.");
    } finally {
      setBusy(null);
    }
  }

  const body = (
    <>
      <div className="top">
        <span className={variant === "bubble" ? "kind" : "meta"}>
          {approval.action_type === "bill_payment" ? "Payment" : "Cancellation"} · {when(approval.requested_at)}
        </span>
        <Chip tone={st.tone}>{st.label}</Chip>
      </div>
      <div className="ttl">{approval.summary}</div>
      <dl className="dl">
        {p.requested_by && (
          <>
            <dt>Asked by</dt>
            <dd>{p.requested_by}</dd>
          </>
        )}
        {p.reference && (
          <>
            <dt>Reference</dt>
            <dd>{p.reference}</dd>
          </>
        )}
      </dl>

      {r?.status === "succeeded" && (
        <p className="foot ok-t">
          Paid · Stripe {r.stripe_payment_intent}
          {r.livemode ? "" : " (test mode — no real money)"}
        </p>
      )}
      {r?.status === "manual_step_required" && (
        <>
          <p className="foot warn-t">{r.next_step}</p>
          {r.cancellation_letter && <pre>{r.cancellation_letter}</pre>}
        </>
      )}
      {r?.status === "failed" && <p className="foot bad-t">Not completed: {r.error} No money moved.</p>}
      {approval.resolution_note && <p className="foot">Note: {approval.resolution_note}</p>}

      {approval.status === "pending" && approval.can_resolve && (
        <div className="approve">
          {canApprove && (
            <button className="bt p" onClick={() => resolve("approve")} disabled={busy !== null}>
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
          )}
          <button className="bt x" onClick={() => resolve("deny")} disabled={busy !== null}>
            {busy === "deny" ? "Blocking…" : "Block"}
          </button>
          {!canApprove && approverPerson && (
            <button className="bt g" onClick={() => void switchPerson(approverPerson.email)}>
              View as {approverPerson.name}
            </button>
          )}
        </div>
      )}
      {approval.status === "pending" && !canApprove && (
        <p className="foot">
          {approver ? `${approver.display_name} decides.` : "Your family approver decides."} Nothing happens until then
          {approval.can_resolve ? " — and you can block it." : "."}
        </p>
      )}
      {error && (
        <p className="foot bad-t" role="alert">
          {error}
        </p>
      )}
    </>
  );

  if (variant === "bubble") {
    return (
      <div className="msg agent">
        <Toy kind="lock" />
        <div className="col" style={{ maxWidth: "min(78%, 460px)" }}>
          <span className="who">Warden</span>
          <div className="abubble">{body}</div>
        </div>
      </div>
    );
  }
  return <div className="card glass">{body}</div>;
}
