"use client";

import { useEffect } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Empty, Notice, Ready, Spinner } from "@/components/ui";
import { useApp } from "@/lib/store";
import type { Approval } from "@/lib/types";

function Approvals() {
  const { data, loading, error, reload, household } = useHouseholdData<Approval[]>("/approvals?household_id={hid}", []);
  const refreshCounts = useApp((s) => s.refreshCounts);
  if (!household) return null;
  const canApprove = household.my_scopes.includes("approve_actions");
  const canView = household.my_scopes.includes("view_accounts");
  const elder = household.members.find((m) => m.role === "elder")?.display_name ?? "The account owner";
  const pending = data.filter((a) => a.status === "pending");
  const done = data.filter((a) => a.status !== "pending");
  const after = () => {
    void reload();
    void refreshCounts();
  };

  return (
    <>
      <p className="lede">
        {canApprove
          ? "Warden asks you before it pays or cancels anything. Approve only what you recognize."
          : "Everything Warden asks your family to approve. You can block anything you didn't ask for."}
      </p>
      {!canView && <Notice>{elder} hasn&apos;t shared their accounts with you yet.</Notice>}
      {error && <Notice tone="err">{error}</Notice>}
      {loading && <Spinner />}
      {!loading && canView && (
        <>
          <h3>Waiting · {pending.length}</h3>
          {pending.length === 0 ? (
            <Empty title="Nothing waiting" body={<p style={{ margin: "4px 0 0" }}>When Warden needs a yes or no, it shows up here.</p>} />
          ) : (
            pending.map((a) => <ApprovalCard key={a.id} approval={a} onResolved={after} />)
          )}
          {done.length > 0 && <h3>History</h3>}
          {done.map((a) => (
            <ApprovalCard key={a.id} approval={a} onResolved={after} />
          ))}
        </>
      )}
    </>
  );
}

export default function ApprovalsPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  const pending = useApp((s) => s.pendingApprovals);
  useEffect(() => setCrumb("Approvals", pending ? `${pending} waiting` : undefined), [setCrumb, pending]);
  return (
    <div className="panel">
      <Ready>
        <Approvals />
      </Ready>
    </div>
  );
}
