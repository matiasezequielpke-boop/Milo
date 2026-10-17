"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { SyncResult } from "@/lib/types";

type PlaidHandler = { open: () => void };
declare global {
  interface Window {
    Plaid?: {
      create: (config: {
        token: string;
        onSuccess: (publicToken: string, metadata: { institution?: { name?: string } | null }) => void;
        onExit?: (err: unknown) => void;
      }) => PlaidHandler;
    };
  }
}

const PLAID_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";

function loadPlaid(): Promise<void> {
  if (window.Plaid) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = PLAID_SCRIPT;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load Plaid."));
    document.head.appendChild(s);
  });
}

export function PlaidConnect({
  householdId,
  sandbox,
  onConnected,
}: {
  householdId: string;
  sandbox: boolean;
  onConnected: (r: SyncResult) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openLink() {
    setBusy(true);
    setError(null);
    try {
      const { link_token } = await api<{ link_token: string }>(`/households/${householdId}/plaid/link-token`, { method: "POST" });
      await loadPlaid();
      window.Plaid!.create({
        token: link_token,
        onSuccess: async (public_token, metadata) => {
          try {
            onConnected(
              await api<SyncResult>(`/households/${householdId}/plaid/exchange`, {
                body: { public_token, institution_name: metadata.institution?.name ?? null },
              }),
            );
          } catch (e) {
            setError(e instanceof Error ? e.message : "Couldn't finish connecting.");
          } finally {
            setBusy(false);
          }
        },
        onExit: () => setBusy(false),
      }).open();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start Plaid.");
      setBusy(false);
    }
  }

  async function sandboxConnect() {
    setBusy(true);
    setError(null);
    try {
      onConnected(await api<SyncResult>(`/households/${householdId}/plaid/sandbox-connect`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't connect the test bank.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="acts" style={{ marginTop: 0 }}>
        <button className="bt p" onClick={openLink} disabled={busy}>
          {busy ? "Connecting…" : "Connect a bank"}
        </button>
        {sandbox && (
          <button className="bt g" onClick={sandboxConnect} disabled={busy}>
            Use Plaid&apos;s test bank
          </button>
        )}
      </div>
      <p className="foot">
        Connections go through Plaid. Warden can read balances and transactions; it can&apos;t move money through this
        connection, and it never sees the bank password.
      </p>
      {error && (
        <p className="foot bad-t" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
