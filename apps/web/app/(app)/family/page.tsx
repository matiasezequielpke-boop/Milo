"use client";

import { useEffect, useState } from "react";

import { Chip, Notice, Ready } from "@/components/ui";
import { api } from "@/lib/api";
import { ALL_SCOPES, SCOPE_TEXT } from "@/lib/consent";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Household, InviteResult, Member, Scope } from "@/lib/types";

/** The account owner's consent, one switch per scope. Saved on each flip
 *  so what's shown is always what's in force. */
function Consent({ household, approver, editable }: { household: Household; approver: Member; editable: boolean }) {
  const refreshHouseholds = useApp((s) => s.refreshHouseholds);
  const showToast = useApp((s) => s.showToast);
  const current = household.consents.find((c) => c.approver_member_id === approver.id && !c.revoked_at);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scopes = current?.scopes ?? [];

  async function flip(s: Scope) {
    let next = scopes.includes(s) ? scopes.filter((x) => x !== s) : [...scopes, s];
    // Approving without seeing the accounts isn't meaningful consent.
    if (s === "approve_actions" && next.includes("approve_actions") && !next.includes("view_accounts")) next = [...next, "view_accounts"];
    if (s === "view_accounts" && !next.includes("view_accounts")) next = next.filter((x) => x !== "approve_actions");
    setBusy(true);
    setError(null);
    try {
      if (next.length === 0) await api(`/households/${household.id}/consents/${approver.id}/revoke`, { method: "POST" });
      else await api(`/households/${household.id}/consents`, { body: { approver_member_id: approver.id, scopes: next } });
      await refreshHouseholds();
      showToast(next.length === 0 ? `${approver.display_name} no longer has access` : `Saved what ${approver.display_name} can do`, "lock");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {ALL_SCOPES.map((s) => {
        const on = scopes.includes(s);
        return (
          <div key={s} className="prow glass">
            <div>
              <b>{SCOPE_TEXT[s].title}</b>
              <span className="d">{SCOPE_TEXT[s].body}</span>
            </div>
            <button
              className={`swt ${on ? "on" : ""}`}
              role="switch"
              aria-checked={on}
              aria-label={SCOPE_TEXT[s].title}
              disabled={!editable || busy}
              onClick={() => flip(s)}
            >
              <i />
            </button>
          </div>
        );
      })}
      {error && <Notice tone="err">{error}</Notice>}
    </>
  );
}

function Family() {
  const household = useActiveHousehold();
  const mode = useApp((s) => s.mode);
  if (!household) return null;
  const isElder = household.my_role === "elder";
  const elder = household.members.find((m) => m.role === "elder");
  const approvers = household.members.filter((m) => m.role === "approver" && m.status !== "removed");

  return (
    <>
      <p className="lede">
        {isElder
          ? "You decide who can see your accounts and approve payments. Change it any time — every change is recorded in Activity."
          : `${elder?.display_name ?? "The account owner"} decides what you can see and do. Every change is recorded in Activity.`}
      </p>

      <h3>People</h3>
      {household.members
        .filter((m) => m.status !== "removed")
        .map((m) => (
          <div key={m.id} className="card glass person">
            <span className="av" aria-hidden="true">
              {m.display_name[0]}
            </span>
            <span className="nm">
              <b>
                {m.display_name}
                {m.is_me && <em> (you)</em>}
              </b>
              <span>{m.email}</span>
            </span>
            <Chip tone={m.role === "elder" ? undefined : m.scopes.includes("approve_actions") ? "ok" : "wait"}>
              {m.role === "elder" ? "Account owner" : m.scopes.length === 0 ? "No access" : "Approver"}
            </Chip>
          </div>
        ))}

      {approvers.map((a) => (
        <section key={a.id}>
          <h3>{isElder ? `What ${a.display_name} can do` : a.is_me ? "What you can do" : `What ${a.display_name} can do`}</h3>
          <Consent household={household} approver={a} editable={isElder} />
          {!isElder && a.is_me && <p className="foot" style={{ color: "var(--ink-3)", fontSize: 12.5 }}>Only {elder?.display_name ?? "the account owner"} can change this.</p>}
        </section>
      ))}

      <h3>Invite family</h3>
      {mode === "demo" ? (
        <Notice>The demo family is fixed: {household.members.map((m) => m.display_name).join(" and ")}.</Notice>
      ) : (
        <InviteForm household={household} />
      )}
    </>
  );
}

function InviteForm({ household }: { household: Household }) {
  const refreshHouseholds = useApp((s) => s.refreshHouseholds);
  const hasOwner = household.members.some((m) => m.role === "elder");
  const [form, setForm] = useState({ email: "", display_name: "" });
  const [result, setResult] = useState<InviteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="card glass"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          setResult(
            await api<InviteResult>(`/households/${household.id}/members`, {
              body: { ...form, role: hasOwner ? "approver" : "elder" },
            }),
          );
          setForm({ email: "", display_name: "" });
          void refreshHouseholds();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Couldn't send the invite.");
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="sub" style={{ margin: "0 0 12px" }}>
        {hasOwner
          ? "Invite a family approver. They can't see anything until the account owner allows it here."
          : "Invite the account owner. Once they join, they decide what you can see and do."}
      </p>
      <label className="fl">
        <span>Their name</span>
        <input required maxLength={120} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
      </label>
      <label className="fl">
        <span>Their email</span>
        <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <span className="hint">Used only to send this invite.</span>
      </label>
      <button className="bt g" type="submit" disabled={busy}>
        {busy ? "Sending…" : "Send invite"}
      </button>
      {result &&
        (result.emailed ? (
          <p className="foot ok-t">Invite emailed to {result.member.email}.</p>
        ) : (
          <p className="foot">
            Email isn&apos;t set up on this server — send this link yourself:{" "}
            <span style={{ userSelect: "all", wordBreak: "break-all", color: "var(--ink)" }}>{result.invite_link}</span>
          </p>
        ))}
      {error && (
        <p className="foot bad-t" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

export default function FamilyPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  useEffect(() => setCrumb("Family"), [setCrumb]);
  return (
    <div className="panel">
      <Ready>
        <Family />
      </Ready>
    </div>
  );
}
