"use client";

import { useState } from "react";

import { Page } from "@/components/Page";
import { useHouseholdData } from "@/components/useHouseholdData";
import { Badge, Button, Card, Empty, Notice, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { day, money } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Alert } from "@/lib/types";

const SEVERITY = { high: "red", medium: "amber", low: "neutral" } as const;
const RESOLVED: Record<string, string> = {
  confirmed_legit: "Marked fine",
  confirmed_fraud: "Marked fraud — payee blocked",
  dismissed: "Dismissed",
};

function AlertCard({ alert, onDone }: { alert: Alert; onDone: () => void }) {
  const household = useApp((s) => s.households.find((h) => h.id === s.activeId));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resolve(resolution: string) {
    setBusy(resolution);
    try {
      await api(`/households/${household!.id}/alerts/${alert.id}/resolve`, { body: { resolution } });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between gap-3">
        <Badge tone={SEVERITY[alert.severity]}>{alert.severity === "high" ? "Likely scam" : alert.severity === "medium" ? "Worth a look" : "FYI"}</Badge>
        <span className="text-sm text-white/40">{day(alert.created_at)}</span>
      </div>
      <p className="text-lg font-medium text-white">{alert.title}</p>
      {alert.transaction && (
        <p className="mt-1 text-white/55">
          {alert.transaction.name} · {money(alert.transaction.amount)} · {day(alert.transaction.date)}
        </p>
      )}
      <ul className="mt-3 list-disc space-y-1 pl-5 text-[0.95rem] text-white/75">
        {alert.reasons.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ul>
      {alert.status === "open" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => resolve("confirmed_legit")} disabled={busy !== null}>
            It&apos;s fine
          </Button>
          <Button variant="danger" onClick={() => resolve("confirmed_fraud")} disabled={busy !== null}>
            It&apos;s fraud
          </Button>
          <Button variant="ghost" onClick={() => resolve("dismissed")} disabled={busy !== null}>
            Dismiss
          </Button>
        </div>
      ) : (
        <p className="mt-3 text-sm text-white/50">{RESOLVED[alert.status]}</p>
      )}
      {alert.status === "open" && alert.severity === "high" && (
        <p className="mt-3 text-sm text-white/50">
          If it&apos;s fraud, also call the bank using the number on the back of the card — they can stop the card and
          dispute the charge.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
    </Card>
  );
}

export default function AlertsPage() {
  const { data, loading, error, reload, household } = useHouseholdData<Alert[]>("alerts?status_filter=all", []);
  const refreshCounts = useApp((s) => s.refreshCounts);
  if (!household) return null;
  const open = data.filter((a) => a.status === "open");
  const resolved = data.filter((a) => a.status !== "open");
  const done = () => {
    void reload();
    void refreshCounts();
  };

  return (
    <Page>
      <PageTitle title="Alerts" subtitle="Charges Warden thinks your family should look at, and why." />
      {!household.my_scopes.includes("view_accounts") && (
        <Notice>The account owner hasn&apos;t shared their accounts with you yet.</Notice>
      )}
      {loading && <Spinner />}
      {error && <Notice tone="red">{error}</Notice>}
      {!loading && !error && (
        <div className="space-y-4">
          {open.length === 0 && (
            <Empty title="All clear" body="Warden checks every new charge after each bank sync. Nothing needs a look right now." />
          )}
          {open.map((a) => (
            <AlertCard key={a.id} alert={a} onDone={done} />
          ))}
          {resolved.length > 0 && <h2 className="pt-6 text-sm uppercase tracking-wider text-white/45">Resolved</h2>}
          {resolved.map((a) => (
            <AlertCard key={a.id} alert={a} onDone={done} />
          ))}
        </div>
      )}
    </Page>
  );
}
