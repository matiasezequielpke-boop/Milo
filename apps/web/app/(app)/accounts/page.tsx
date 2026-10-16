"use client";

import { useState } from "react";

import { Page } from "@/components/Page";
import { PlaidConnect } from "@/components/PlaidConnect";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Badge, Button, Card, Empty, Field, Notice, PageTitle, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { cadence, day, money } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Account, Bill, Subscription, SyncResult, Transaction } from "@/lib/types";

const BILL_STATUS: Record<string, { label: string; tone: "neutral" | "amber" | "green" | "red" }> = {
  open: { label: "To pay", tone: "neutral" },
  pending_approval: { label: "Waiting for approval", tone: "amber" },
  processing: { label: "Processing", tone: "amber" },
  paid: { label: "Paid", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm uppercase tracking-wider text-white/45">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function MoneyPage() {
  const integrations = useApp((s) => s.integrations);
  const refreshCounts = useApp((s) => s.refreshCounts);
  const accounts = useHouseholdData<Account[]>("accounts", []);
  const bills = useHouseholdData<Bill[]>("bills", []);
  const subs = useHouseholdData<Subscription[]>("subscriptions", []);
  const txns = useHouseholdData<Transaction[]>("transactions?days=30", []);
  const household = accounts.household;
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bill, setBill] = useState({ payee_name: "", amount: "", due_date: "", reference: "" });
  const [sim, setSim] = useState({ description: "GIFT CARD MALL #3", amount: "500.00" });

  if (!household) return null;
  if (!household.my_scopes.includes("view_accounts")) {
    return (
      <Page>
        <PageTitle title="Money" />
        <Notice>The account owner hasn&apos;t shared their accounts with you yet. They can do it on the Family page.</Notice>
      </Page>
    );
  }

  const reloadAll = () => {
    void accounts.reload();
    void bills.reload();
    void subs.reload();
    void txns.reload();
    void refreshCounts();
  };
  const synced = (r: SyncResult) => {
    setSyncNote(
      `Synced ${r.accounts} account${r.accounts === 1 ? "" : "s"}, ${r.added} new transaction${r.added === 1 ? "" : "s"}` +
        (r.new_alerts ? ` — ${r.new_alerts} new alert${r.new_alerts === 1 ? "" : "s"}.` : "."),
    );
    reloadAll();
  };

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(key);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const base = `/households/${household.id}`;
  const sandbox = Boolean(integrations?.plaid) && integrations?.plaid_env === "sandbox";

  return (
    <Page>
      <PageTitle
        title="Money"
        subtitle={`${household.name}: accounts, bills, and recurring charges.`}
        action={
          accounts.data.length > 0 && (
            <Button variant="secondary" disabled={busy !== null} onClick={() => run("sync", async () => synced(await api<SyncResult>(`${base}/sync`, { method: "POST" })))}>
              {busy === "sync" ? "Syncing…" : "Sync now"}
            </Button>
          )
        }
      />
      {integrations && !integrations.plaid && (
        <div className="mb-6">
          <Notice tone="amber">Bank connections are off on this server until Plaid keys are configured (PLAID_CLIENT_ID / PLAID_SECRET).</Notice>
        </div>
      )}
      {syncNote && <div className="mb-6"><Notice>{syncNote}</Notice></div>}
      {error && <div className="mb-6"><Notice tone="red">{error}</Notice></div>}

      <div className="space-y-10">
        <Section title="Accounts">
          {accounts.loading ? (
            <Spinner />
          ) : accounts.data.length === 0 ? (
            <Card>
              <p className="mb-4 text-lg text-white">Connect {household.members.find((m) => m.role === "elder")?.display_name ?? "the owner"}&apos;s bank</p>
              <PlaidConnect householdId={household.id} sandbox={sandbox} onConnected={synced} />
            </Card>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {accounts.data.map((a) => (
                <Card key={a.id}>
                  <p className="text-white/55">
                    {a.institution_name} · {a.subtype || a.type} {a.mask && `••${a.mask}`}
                  </p>
                  <p className="mt-1 text-white">{a.name}</p>
                  <p className="mt-3 text-2xl font-semibold text-white">{money(a.current_balance, a.currency)}</p>
                  {a.available_balance && <p className="text-sm text-white/45">{money(a.available_balance, a.currency)} available</p>}
                </Card>
              ))}
            </div>
          )}
        </Section>

        <Section title="Bills">
          <Card>
            <form
              className="grid gap-3 sm:grid-cols-[2fr,1fr,1fr]"
              onSubmit={(e) => {
                e.preventDefault();
                void run("bill", async () => {
                  await api(`${base}/bills`, {
                    body: {
                      payee_name: bill.payee_name,
                      amount: bill.amount,
                      due_date: bill.due_date || null,
                      reference: bill.reference || null,
                    },
                  });
                  setBill({ payee_name: "", amount: "", due_date: "", reference: "" });
                  void bills.reload();
                });
              }}
            >
              <Field label="Who is owed">
                <input required className={inputClass} value={bill.payee_name} placeholder="ConEd" onChange={(e) => setBill({ ...bill, payee_name: e.target.value })} />
              </Field>
              <Field label="Amount ($)">
                <input required inputMode="decimal" pattern="^\d+(\.\d{1,2})?$" className={inputClass} value={bill.amount} placeholder="84.20" onChange={(e) => setBill({ ...bill, amount: e.target.value })} />
              </Field>
              <Field label="Due">
                <input type="date" className={inputClass} value={bill.due_date} onChange={(e) => setBill({ ...bill, due_date: e.target.value })} />
              </Field>
              <Field label="Account / invoice number (optional)">
                <input className={inputClass} value={bill.reference} onChange={(e) => setBill({ ...bill, reference: e.target.value })} />
              </Field>
              <div className="flex items-end sm:col-span-2">
                <Button type="submit" variant="secondary" disabled={busy !== null}>
                  Add bill
                </Button>
              </div>
            </form>
          </Card>
          {bills.data.length === 0 && !bills.loading && <Empty title="No bills yet" body="Add one here, or just tell Milo in the chat." />}
          {bills.data.map((b) => (
            <Card key={b.id} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-white">
                  {b.payee_name} · <span className="font-semibold">{money(b.amount, b.currency)}</span>
                </p>
                <p className="text-sm text-white/45">
                  {b.due_date ? `Due ${day(b.due_date)}` : "No due date"}
                  {b.reference && ` · ${b.reference}`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {b.payee_blocked ? <Badge tone="red">Blocked payee</Badge> : <Badge tone={BILL_STATUS[b.status]?.tone ?? "neutral"}>{BILL_STATUS[b.status]?.label ?? b.status}</Badge>}
                {(b.status === "open" || b.status === "failed") && !b.payee_blocked && (
                  <Button
                    variant="secondary"
                    disabled={busy !== null}
                    onClick={() =>
                      run(`pay-${b.id}`, async () => {
                        await api(`${base}/bills/${b.id}/request-payment`, { method: "POST" });
                        void bills.reload();
                        void refreshCounts();
                      })
                    }
                  >
                    Ask to pay
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </Section>

        <Section title="Recurring charges">
          {subs.data.length === 0 && !subs.loading && <Empty title="None detected yet" body="Warden spots subscriptions from the transaction history after a bank sync." />}
          {subs.data.map((s) => (
            <Card key={s.id} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-white">
                  {s.merchant_name} · <span className="font-semibold">{money(s.last_amount)}</span> {cadence(s.cadence_days)}
                </p>
                <p className="text-sm text-white/45">
                  Charged {s.charge_count} times · last {day(s.last_charged_on)}
                </p>
              </div>
              {s.kind === "bill" ? (
                <Badge>Recurring bill</Badge>
              ) : s.status === "active" ? (
                <Button
                  variant="secondary"
                  disabled={busy !== null}
                  onClick={() =>
                    run(`cancel-${s.id}`, async () => {
                      await api(`${base}/subscriptions/${s.id}/request-cancel`, { method: "POST" });
                      void subs.reload();
                      void refreshCounts();
                    })
                  }
                >
                  Ask to cancel
                </Button>
              ) : (
                <Badge tone="amber">{s.status === "cancel_requested" ? "Cancellation requested" : s.status}</Badge>
              )}
            </Card>
          ))}
        </Section>

        <Section title="Last 30 days">
          {txns.data.length === 0 && !txns.loading && <Empty title="No transactions yet" />}
          {txns.data.length > 0 && (
            <div className="divide-y divide-white/10 rounded-2xl border border-white/10">
              {txns.data.map((t) => (
                <div key={t.id} className="flex items-center justify-between gap-4 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-white">{t.merchant_name || t.name}</p>
                    <p className="text-sm text-white/40">
                      {day(t.date)}
                      {t.pending && " · pending"}
                    </p>
                  </div>
                  <p className={`shrink-0 tabular-nums ${Number(t.amount) < 0 ? "text-emerald-300" : "text-white"}`}>
                    {Number(t.amount) < 0 ? "+" : "−"}
                    {money(Math.abs(Number(t.amount)), t.currency)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Section>

        {sandbox && accounts.data.length > 0 && (
          <Section title="Sandbox: simulate a charge">
            <Card>
              <p className="mb-4 text-white/60">
                Adds a real transaction at Plaid&apos;s test bank and syncs it, so you can watch detection → alert → approval
                end to end. Sandbox only.
              </p>
              <form
                className="grid gap-3 sm:grid-cols-[2fr,1fr,auto]"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run("sim", async () => synced(await api<SyncResult>(`${base}/plaid/sandbox-transactions`, { body: sim })));
                }}
              >
                <Field label="Description">
                  <input className={inputClass} value={sim.description} onChange={(e) => setSim({ ...sim, description: e.target.value })} />
                </Field>
                <Field label="Amount ($)">
                  <input className={inputClass} value={sim.amount} onChange={(e) => setSim({ ...sim, amount: e.target.value })} />
                </Field>
                <div className="flex items-end">
                  <Button type="submit" variant="secondary" disabled={busy !== null}>
                    {busy === "sim" ? "Adding…" : "Add charge"}
                  </Button>
                </div>
              </form>
            </Card>
          </Section>
        )}
      </div>
    </Page>
  );
}
