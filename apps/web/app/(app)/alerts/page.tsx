"use client";

import { useEffect, useState } from "react";

import { useHouseholdData } from "@/components/useHouseholdData";
import { Chip, Empty, Notice, Ready, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { day, money } from "@/lib/format";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Alert } from "@/lib/types";

const SEVERITY = {
  high: { label: "Likely scam", tone: "bad" as const },
  medium: { label: "Worth a look", tone: "wait" as const },
  low: { label: "FYI", tone: undefined },
};
const RESOLVED: Record<string, string> = {
  confirmed_legit: "Marked as fine",
  confirmed_fraud: "Marked as fraud — Warden won't pay this payee",
  dismissed: "Dismissed",
};

function AlertCard({ alert, onDone }: { alert: Alert; onDone: () => void }) {
  const household = useActiveHousehold();
  const showToast = useApp((s) => s.showToast);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sev = SEVERITY[alert.severity];

  async function resolve(resolution: string) {
    setBusy(resolution);
    setError(null);
    try {
      await api(`/households/${household!.id}/alerts/${alert.id}/resolve`, { body: { resolution } });
      showToast(RESOLVED[resolution] ?? "Saved", "star");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card glass">
      <div className="top">
        <Chip tone={sev.tone}>{sev.label}</Chip>
        <span className="meta">{day(alert.created_at)}</span>
      </div>
      <div className="ttl">{alert.title}</div>
      {alert.transaction && (
        <div className="sub">
          {alert.transaction.name} · {money(alert.transaction.amount)} · {day(alert.transaction.date)}
        </div>
      )}
      <ul className="why">
        {alert.reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      {alert.status === "open" ? (
        <div className="acts">
          <button className="bt g sm" onClick={() => resolve("confirmed_legit")} disabled={busy !== null}>
            It&apos;s fine
          </button>
          <button className="bt x sm" onClick={() => resolve("confirmed_fraud")} disabled={busy !== null}>
            It&apos;s fraud
          </button>
          <button className="bt g sm" onClick={() => resolve("dismissed")} disabled={busy !== null}>
            Dismiss
          </button>
        </div>
      ) : (
        <p className="foot">{RESOLVED[alert.status]}</p>
      )}
      {alert.status === "open" && alert.severity === "high" && (
        <p className="foot">
          If it&apos;s fraud, also call the bank on the number on the back of the card — they can stop the card and dispute the
          charge.
        </p>
      )}
      {error && (
        <p className="foot bad-t" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function Alerts() {
  const { data, loading, error, reload, household } = useHouseholdData<Alert[]>("alerts?status_filter=all", []);
  const refreshCounts = useApp((s) => s.refreshCounts);
  if (!household) return null;
  const open = data.filter((a) => a.status === "open");
  const resolved = data.filter((a) => a.status !== "open");
  const done = () => {
    void reload();
    void refreshCounts();
  };
  const elder = household.members.find((m) => m.role === "elder")?.display_name ?? "The account owner";

  return (
    <>
      <p className="lede">Charges Sentinel thinks the family should look at, and why.</p>
      {!household.my_scopes.includes("view_accounts") && <Notice>{elder} hasn&apos;t shared their accounts with you yet.</Notice>}
      {loading && <Spinner />}
      {error && <Notice tone="err">{error}</Notice>}
      {!loading && !error && (
        <>
          <h3>Open · {open.length}</h3>
          {open.length === 0 && (
            <Empty
              title="All clear"
              body={<p style={{ margin: "4px 0 0" }}>Sentinel checks every new charge after each bank sync. Nothing needs a look right now.</p>}
            />
          )}
          {open.map((a) => (
            <AlertCard key={a.id} alert={a} onDone={done} />
          ))}
          {resolved.length > 0 && <h3>Resolved</h3>}
          {resolved.map((a) => (
            <AlertCard key={a.id} alert={a} onDone={done} />
          ))}
        </>
      )}
    </>
  );
}

export default function AlertsPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  const open = useApp((s) => s.openAlerts);
  useEffect(() => setCrumb("Alerts", open ? `${open} open` : undefined), [setCrumb, open]);
  return (
    <div className="panel">
      <Ready>
        <Alerts />
      </Ready>
    </div>
  );
}
