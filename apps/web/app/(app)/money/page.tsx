"use client";

import { useEffect, useState } from "react";

import { PlaidConnect } from "@/components/PlaidConnect";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Chip, Empty, Notice, Ready, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { cadence, day, money } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Account, Bill, Subscription, SyncResult, Transaction } from "@/lib/types";

const BILL_STATUS: Record<string, { label: string; tone?: "ok" | "wait" | "bad" }> = {
  open: { label: "To pay" },
  pending_approval: { label: "Waiting for approval", tone: "wait" },
  processing: { label: "Processing", tone: "wait" },
  paid: { label: "Paid", tone: "ok" },
  failed: { label: "Failed — can retry", tone: "bad" },
  cancelled: { label: "Cancelled" },
};

function Money() {
  const integrations = useApp((s) => s.integrations);
  const refreshCounts = useApp((s) => s.refreshCounts);
  const showToast = useApp((s) => s.showToast);
  const accounts = useHouseholdData<Account[]>("accounts", []);
  const bills = useHouseholdData<Bill[]>("bills", []);
  const subs = useHouseholdData<Subscription[]>("subscriptions", []);
  const txns = useHouseholdData<Transaction[]>("transactions?days=30", []);
  const household = accounts.household;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bill, setBill] = useState({ payee_name: "", amount: "", due_date: "", reference: "" });
  const [sim, setSim] = useState({ description: "GIFT CARD MALL #3", amount: "500.00" });

  if (!household) return null;
  const elder = household.members.find((m) => m.role === "elder")?.display_name ?? "the account owner";
  if (!household.my_scopes.includes("view_accounts")) {
    return <Notice>{elder} hasn&apos;t shared their accounts with you yet. They can do it on the Family page.</Notice>;
  }

  const reloadAll = () => {
    void accounts.reload();
    void bills.reload();
    void subs.reload();
    void txns.reload();
    void refreshCounts();
  };
  const synced = (r: SyncResult) => {
    showToast(
      `Synced ${r.added} new transaction${r.added === 1 ? "" : "s"}` + (r.new_alerts ? ` · ${r.new_alerts} new alert${r.new_alerts === 1 ? "" : "s"}` : ""),
      r.new_alerts ? "star" : "beacon",
    );
    reloadAll();
  };

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const base = `/households/${household.id}`;
  const sandbox = Boolean(integrations?.plaid) && integrations?.plaid_env === "sandbox";

  return (
    <>
      <p className="lede">{household.name}: accounts, bills and recurring charges.</p>
      {integrations && !integrations.plaid && (
        <Notice tone="warn">Bank connections are off on this server until Plaid keys are configured.</Notice>
      )}
      {error && <Notice tone="err">{error}</Notice>}

      <h3>
        Accounts
        <span className="sp" />
        {accounts.data.length > 0 && integrations?.plaid && (
          <button
            className="bt g sm"
            disabled={busy !== null}
            onClick={() => run("sync", async () => synced(await api<SyncResult>(`${base}/sync`, { method: "POST" })))}
          >
            {busy === "sync" ? "Syncing…" : "Sync now"}
          </button>
        )}
      </h3>
      {accounts.loading ? (
        <Spinner />
      ) : accounts.data.length === 0 ? (
        <div className="card glass">
          <div className="ttl" style={{ marginBottom: 12 }}>
            Connect {elder}&apos;s bank
          </div>
          <PlaidConnect householdId={household.id} sandbox={sandbox} onConnected={synced} />
        </div>
      ) : (
        <div className="accts">
          {accounts.data.map((a) => (
            <div key={a.id} className="acct glass">
              <div className="meta">
                {a.institution_name} · {a.subtype || a.type} {a.mask && `••${a.mask}`}
              </div>
              <div className="nm">{a.name}</div>
              <b>{money(a.current_balance, a.currency)}</b>
              {a.available_balance && <div className="avail">{money(a.available_balance, a.currency)} available</div>}
            </div>
          ))}
        </div>
      )}

      <h3>Bills</h3>
      {bills.data.map((b) => {
        const st = BILL_STATUS[b.status] ?? { label: b.status };
        return (
          <div key={b.id} className="lrow glass">
            <div className="l">
              <b>
                {b.payee_name} · {money(b.amount, b.currency)}
              </b>
              <span>
                {b.due_date ? `Due ${day(b.due_date)}` : "No due date"}
                {b.reference && ` · ${b.reference}`}
              </span>
            </div>
            <div className="r">
              {b.payee_blocked ? <Chip tone="bad">Blocked payee</Chip> : <Chip tone={st.tone}>{st.label}</Chip>}
              {(b.status === "open" || b.status === "failed") && !b.payee_blocked && (
                <button
                  className="bt p sm"
                  disabled={busy !== null}
                  onClick={() =>
                    run(`pay-${b.id}`, async () => {
                      await api(`${base}/bills/${b.id}/request-payment`, { method: "POST" });
                      showToast("Sent to the family for approval. Nothing is paid yet.", "lock");
                      void bills.reload();
                      void refreshCounts();
                    })
                  }
                >
                  Ask to pay
                </button>
              )}
            </div>
          </div>
        );
      })}
      {bills.data.length === 0 && !bills.loading && (
        <Empty title="No bills yet" body={<p style={{ margin: "4px 0 0" }}>Add one below, or just tell Milo in the chat.</p>} />
      )}
      <form
        className="card glass form"
        onSubmit={(e) => {
          e.preventDefault();
          void run("bill", async () => {
            await api(`${base}/bills`, {
              body: { payee_name: bill.payee_name, amount: bill.amount, due_date: bill.due_date || null, reference: bill.reference || null },
            });
            setBill({ payee_name: "", amount: "", due_date: "", reference: "" });
            showToast("Bill added", "beacon");
            void bills.reload();
          });
        }}
      >
        <label className="fl">
          <span>Who is owed</span>
          <input required value={bill.payee_name} placeholder="ConEd" onChange={(e) => setBill({ ...bill, payee_name: e.target.value })} />
        </label>
        <label className="fl">
          <span>Amount ($)</span>
          <input
            required
            inputMode="decimal"
            pattern="^\d+(\.\d{1,2})?$"
            value={bill.amount}
            placeholder="84.20"
            onChange={(e) => setBill({ ...bill, amount: e.target.value })}
          />
        </label>
        <label className="fl">
          <span>Due</span>
          <input type="date" value={bill.due_date} onChange={(e) => setBill({ ...bill, due_date: e.target.value })} />
        </label>
        <label className="fl wide">
          <span>Account or invoice number (optional)</span>
          <input value={bill.reference} onChange={(e) => setBill({ ...bill, reference: e.target.value })} />
        </label>
        <div className="fl">
          <button type="submit" className="bt g" disabled={busy !== null} style={{ width: "100%" }}>
            {busy === "bill" ? "Adding…" : "Add bill"}
          </button>
        </div>
      </form>

      <h3>Recurring charges</h3>
      {subs.data.length === 0 && !subs.loading && (
        <Empty
          title="None detected yet"
          body={<p style={{ margin: "4px 0 0" }}>Sentinel spots subscriptions from the transaction history after a bank sync.</p>}
        />
      )}
      {subs.data.map((s) => (
        <div key={s.id} className="lrow glass">
          <div className="l">
            <b>
              {s.merchant_name} · {money(s.last_amount)} {cadence(s.cadence_days)}
            </b>
            <span>
              Charged {s.charge_count} times · last {day(s.last_charged_on)}
            </span>
          </div>
          <div className="r">
            {s.kind === "bill" ? (
              <Chip>Recurring bill</Chip>
            ) : s.status === "active" ? (
              <button
                className="bt g sm"
                disabled={busy !== null}
                onClick={() =>
                  run(`cancel-${s.id}`, async () => {
                    await api(`${base}/subscriptions/${s.id}/request-cancel`, { method: "POST" });
                    showToast("Sent to the family for approval.", "lock");
                    void subs.reload();
                    void refreshCounts();
                  })
                }
              >
                Ask to cancel
              </button>
            ) : (
              <Chip tone="wait">{s.status === "cancel_requested" ? "Cancellation requested" : s.status}</Chip>
            )}
          </div>
        </div>
      ))}

      <h3>Last 30 days</h3>
      {txns.data.length === 0 && !txns.loading && <Empty title="No transactions yet" />}
      {txns.data.length > 0 && (
        <div className="txs glass">
          {txns.data.map((t) => (
            <div key={t.id} className="tx">
              <div className="l">
                <b>{t.merchant_name || t.name}</b>
                <span>
                  {day(t.date)}
                  {t.pending && " · pending"}
                </span>
              </div>
              <span className={`amt ${Number(t.amount) < 0 ? "in" : ""}`}>
                {Number(t.amount) < 0 ? "+" : "−"}
                {money(Math.abs(Number(t.amount)), t.currency)}
              </span>
            </div>
          ))}
        </div>
      )}

      {sandbox && accounts.data.length > 0 && (
        <>
          <h3>Sandbox · simulate a charge</h3>
          <form
            className="card glass form"
            onSubmit={(e) => {
              e.preventDefault();
              void run("sim", async () => synced(await api<SyncResult>(`${base}/plaid/sandbox-transactions`, { body: sim })));
            }}
          >
            <p className="sub wide" style={{ gridColumn: "1 / -1", margin: "0 0 12px" }}>
              Adds a real transaction at Plaid&apos;s test bank and syncs it, so you can watch detection → alert → approval end to
              end. Test bank only.
            </p>
            <label className="fl">
              <span>Description</span>
              <input value={sim.description} onChange={(e) => setSim({ ...sim, description: e.target.value })} />
            </label>
            <label className="fl">
              <span>Amount ($)</span>
              <input value={sim.amount} onChange={(e) => setSim({ ...sim, amount: e.target.value })} />
            </label>
            <div className="fl">
              <button type="submit" className="bt g" disabled={busy !== null} style={{ width: "100%" }}>
                {busy === "sim" ? "Adding…" : "Add charge"}
              </button>
            </div>
          </form>
        </>
      )}
    </>
  );
}

export default function MoneyPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  useEffect(() => setCrumb("Money"), [setCrumb]);
  return (
    <div className="panel">
      <Ready>
        <Money />
      </Ready>
    </div>
  );
}
