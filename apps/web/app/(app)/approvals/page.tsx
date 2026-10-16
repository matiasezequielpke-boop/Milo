"use client";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Page } from "@/components/Page";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Empty, Notice, PageTitle, Spinner } from "@/components/ui";
import { useApp } from "@/lib/store";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const { data, loading, error, reload, household } = useHouseholdData<Approval[]>("/approvals?household_id={hid}", []);
  const refreshCounts = useApp((s) => s.refreshCounts);
  if (!household) return null;
  const canApprove = household.my_scopes.includes("approve_actions");
  const canView = household.my_scopes.includes("view_accounts");
  const pending = data.filter((a) => a.status === "pending");
  const done = data.filter((a) => a.status !== "pending");

  return (
    <Page>
      <PageTitle
        title="Approvals"
        subtitle={
          canApprove
            ? "Warden asks you before it pays or cancels anything. Approve only what you recognize."
            : "Everything Warden asks your family to approve. You can block anything you didn't ask for."
        }
      />
      {!canView && <Notice>The account owner hasn&apos;t shared their accounts with you yet.</Notice>}
      {loading && <Spinner />}
      {error && <Notice tone="red">{error}</Notice>}
      {!loading && canView && (
        <div className="space-y-10">
          <section className="space-y-4">
            <h2 className="text-sm uppercase tracking-wider text-white/45">Waiting ({pending.length})</h2>
            {pending.length === 0 ? (
              <Empty title="Nothing waiting" body="When Warden needs a yes or no, it shows up here and you'll get an email." />
            ) : (
              pending.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approval={a}
                  canApprove={canApprove}
                  onResolved={() => {
                    void reload();
                    void refreshCounts();
                  }}
                />
              ))
            )}
          </section>
          {done.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-sm uppercase tracking-wider text-white/45">History</h2>
              {done.map((a) => (
                <ApprovalCard key={a.id} approval={a} canApprove={false} onResolved={() => reload()} />
              ))}
            </section>
          )}
        </div>
      )}
    </Page>
  );
}
