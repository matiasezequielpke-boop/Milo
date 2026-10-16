"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { when } from "@/lib/format";
import type { Approval } from "@/lib/types";
import { Badge, Button, ShieldIcon } from "@/components/ui";

const STATUS: Record<Approval["status"], { label: string; tone: "neutral" | "red" | "amber" | "green" }> = {
  pending: { label: "Waiting for approval", tone: "amber" },
  approved: { label: "Approved", tone: "green" },
  denied: { label: "Blocked", tone: "red" },
  expired: { label: "Expired", tone: "neutral" },
};

export function ApprovalCard({
  approval,
  canApprove,
  onResolved,
}: {
  approval: Approval;
  canApprove: boolean;
  onResolved: (a: Approval) => void;
}) {
  const [busy, setBusy] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const result = approval.execution_result as Record<string, string> | null;
  const status =
    approval.status === "approved" && result?.status === "failed"
      ? { label: "Approved — not completed", tone: "red" as const }
      : STATUS[approval.status];
  const p = approval.payload as Record<string, string | null>;

  async function resolve(kind: "approve" | "deny") {
    setBusy(kind);
    setError(null);
    try {
      onResolved(await api<Approval>(`/approvals/${approval.id}/${kind}`, { method: "POST", body: {} }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't do that.");
    } finally {
      setBusy(null);
    }
  }

  return (
    // Deliberately flat and high-contrast: this is the moment money moves.
    <div className="rounded-2xl border border-white/20 bg-ink-850 p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm text-white/60">
          <ShieldIcon /> Warden · {approval.action_type === "bill_payment" ? "Payment" : "Cancellation"}
        </span>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      <p className="text-lg font-medium leading-snug text-white">{approval.summary}</p>
      <dl className="mt-3 grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm text-white/60">
        {p.requested_by && (
          <>
            <dt>Asked by</dt>
            <dd className="text-white/85">{p.requested_by}</dd>
          </>
        )}
        {p.reference && (
          <>
            <dt>Reference</dt>
            <dd className="text-white/85">{p.reference}</dd>
          </>
        )}
        <dt>Requested</dt>
        <dd className="text-white/85">{when(approval.requested_at)}</dd>
      </dl>

      {result?.status === "succeeded" && (
        <p className="mt-3 text-sm text-emerald-300">
          Paid · Stripe {result.stripe_payment_intent}
          {result.livemode ? "" : " (test mode — no real money)"}
        </p>
      )}
      {result?.status === "manual_step_required" && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-amber-200">{result.next_step}</p>
          <pre className="whitespace-pre-wrap rounded-xl bg-black p-3 text-white/80">{result.cancellation_letter}</pre>
        </div>
      )}
      {result?.status === "failed" && <p className="mt-3 text-sm text-red-300">Not completed: {result.error}</p>}
      {approval.resolution_note && <p className="mt-2 text-sm text-white/55">Note: {approval.resolution_note}</p>}

      {approval.status === "pending" && approval.can_resolve && (
        <div className="mt-4 flex flex-wrap gap-2">
          {canApprove && (
            <Button onClick={() => resolve("approve")} disabled={busy !== null}>
              {busy === "approve" ? "Approving…" : "Approve"}
            </Button>
          )}
          <Button variant="danger" onClick={() => resolve("deny")} disabled={busy !== null}>
            {busy === "deny" ? "Blocking…" : "Block"}
          </Button>
        </div>
      )}
      {approval.status === "pending" && !canApprove && (
        <p className="mt-3 text-sm text-white/50">Your family approver decides. Nothing happens until they do.</p>
      )}
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
    </div>
  );
}
