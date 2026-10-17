"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { IconDownload } from "@/components/icons";
import { Notice, Ready } from "@/components/ui";
import { api, apiBlob } from "@/lib/api";
import { LEGAL_LINKS } from "@/lib/legal";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Me } from "@/lib/types";

function Settings() {
  const router = useRouter();
  const { me, mode, integrations, showToast, signOut } = useApp();
  const household = useActiveHousehold();
  const [optOut, setOptOut] = useState(Boolean(me?.email_opt_out_at));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");
  const demo = mode === "demo";
  const isOwner = household?.my_role === "elder";

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

  return (
    <>
      {error && <Notice tone="err">{error}</Notice>}

      <h3>Account</h3>
      <div className="prow glass">
        <div>
          <b>{me?.email}</b>
          <span className="d">{demo ? "Demo family — not a real account." : "Logging in always takes your password and a code we email you."}</span>
        </div>
        <button
          className="bt g sm"
          onClick={async () => {
            await signOut();
            router.replace("/login");
          }}
        >
          {demo ? "Leave the demo" : "Log out"}
        </button>
      </div>

      <h3>Notifications</h3>
      <div className="prow glass">
        <div>
          <b>Notification emails</b>
          <span className="d">Approval requests, suspicious-charge alerts and what happened after a decision. Sign-in codes always arrive.</span>
        </div>
        <button
          className={`swt ${optOut ? "" : "on"}`}
          role="switch"
          aria-checked={!optOut}
          aria-label="Notification emails"
          disabled={busy !== null}
          onClick={() =>
            run("notify", async () => {
              const updated = await api<Me>("/me/notifications", { method: "PUT", body: { email_notifications: optOut } });
              setOptOut(Boolean(updated.email_opt_out_at));
              useApp.setState({ me: updated });
              showToast(updated.email_opt_out_at ? "Notification emails off" : "Notification emails on", "beacon");
            })
          }
        >
          <i />
        </button>
      </div>

      <h3>Your data</h3>
      <div className="prow glass">
        <div>
          <b>Download your data</b>
          <span className="d">
            Everything Warden holds about you, as a file you can keep{isOwner ? " — including your accounts, transactions, alerts, bills and activity" : ""}.
          </span>
        </div>
        <button
          className="bt g sm"
          disabled={busy !== null}
          onClick={() =>
            run("export", async () => {
              const blob = await apiBlob("/me/export");
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "warden-my-data.json";
              a.click();
              URL.revokeObjectURL(url);
            })
          }
        >
          <IconDownload />
          {busy === "export" ? "Preparing…" : "Download"}
        </button>
      </div>

      <h3>Delete your account</h3>
      <div className="card glass danger">
        <p style={{ margin: "0 0 8px", fontSize: 14 }}>
          {isOwner
            ? "This deletes your account and everything in it: your bank connections (also removed at Plaid), accounts, transactions, alerts, bills, approvals, chats and the activity log. Family members lose access."
            : "This deletes your account, your chats and your access to the family's accounts. The account owner's activity log keeps your name next to decisions you already made, because they need that record."}{" "}
          It can&apos;t be undone. You can download your data first.
        </p>
        {demo ? (
          <p className="foot">The demo family can&apos;t be deleted.</p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run("delete", async () => {
                const result = await api<{ problems: string[] }>("/me", { method: "DELETE", body: { confirm: "DELETE" } });
                if (result.problems.length) window.alert(result.problems.join("\n"));
                await signOut();
                router.replace("/login?deleted=1");
              });
            }}
          >
            <label className="fl" style={{ marginTop: 10 }}>
              <span>Type DELETE to confirm</span>
              <input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
            </label>
            {integrations && !integrations.account_deletion && (
              <Notice tone="warn">Account deletion isn&apos;t switched on for this server yet. If it fails, email us and we&apos;ll do it by hand.</Notice>
            )}
            <button className="bt x" type="submit" disabled={confirm !== "DELETE" || busy !== null}>
              {busy === "delete" ? "Deleting…" : "Delete my account"}
            </button>
          </form>
        )}
      </div>

      <h3>Legal</h3>
      <div className="prow glass">
        <div>
          <b>Policies</b>
          <span className="d">
            {LEGAL_LINKS.map((l, i) => (
              <span key={l.href}>
                {i > 0 && " · "}
                <Link href={l.href} style={{ textDecoration: "underline" }}>
                  {l.label}
                </Link>
              </span>
            ))}
          </span>
        </div>
      </div>
    </>
  );
}

export default function SettingsPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  useEffect(() => setCrumb("Settings"), [setCrumb]);
  return (
    <div className="panel">
      <Ready>
        <Settings />
      </Ready>
    </div>
  );
}
