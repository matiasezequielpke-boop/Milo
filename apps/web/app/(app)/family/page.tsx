"use client";

import { useState } from "react";

import { Page } from "@/components/Page";
import { Badge, Button, Card, Field, Notice, PageTitle, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { ALL_SCOPES, SCOPE_TEXT } from "@/lib/consent";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Household, InviteResult, Member, Scope } from "@/lib/types";

function ConsentEditor({ household, approver, onSaved }: { household: Household; approver: Member; onSaved: () => void }) {
  const current = household.consents.find((c) => c.approver_member_id === approver.id && !c.revoked_at);
  const [scopes, setScopes] = useState<Scope[]>(current?.scopes ?? ALL_SCOPES);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(s: Scope) {
    setScopes((list) => {
      let next = list.includes(s) ? list.filter((x) => x !== s) : [...list, s];
      // Approving without seeing the accounts isn't meaningful consent.
      if (s === "approve_actions" && next.includes("approve_actions") && !next.includes("view_accounts")) next = [...next, "view_accounts"];
      if (s === "view_accounts" && !next.includes("view_accounts")) next = next.filter((x) => x !== "approve_actions");
      return next;
    });
  }

  async function save(kind: "grant" | "revoke") {
    setBusy(true);
    setError(null);
    try {
      if (kind === "grant") {
        await api(`/households/${household.id}/consents`, { body: { approver_member_id: approver.id, scopes } });
      } else {
        await api(`/households/${household.id}/consents/${approver.id}/revoke`, { method: "POST" });
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 space-y-3 border-t border-white/10 pt-4">
      <p className="text-white/70">What can {approver.display_name} do?</p>
      {ALL_SCOPES.map((s) => (
        <label key={s} className="flex cursor-pointer gap-3 rounded-xl border border-white/10 p-3 hover:border-white/25">
          <input type="checkbox" className="mt-1 h-5 w-5 accent-white" checked={scopes.includes(s)} onChange={() => toggle(s)} />
          <span>
            <span className="block text-white">{SCOPE_TEXT[s].title}</span>
            <span className="block text-sm text-white/55">{SCOPE_TEXT[s].body}</span>
          </span>
        </label>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save("grant")} disabled={busy || scopes.length === 0}>
          {current ? "Save changes" : "Allow"}
        </Button>
        {current && (
          <Button variant="danger" onClick={() => save("revoke")} disabled={busy}>
            Remove all access
          </Button>
        )}
      </div>
      <p className="text-sm text-white/40">You can change or remove this at any time. Every change is recorded in Activity.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
    </div>
  );
}

export default function FamilyPage() {
  const household = useActiveHousehold();
  const refreshHouseholds = useApp((s) => s.refreshHouseholds);
  const [invite, setInvite] = useState({ email: "", display_name: "" });
  const [inviteResult, setInviteResult] = useState<InviteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!household) return null;

  const isElder = household.my_role === "elder";
  const elder = household.members.find((m) => m.role === "elder");
  const approvers = household.members.filter((m) => m.role === "approver");
  const inviteRole = elder ? "approver" : "elder";

  return (
    <Page>
      <PageTitle
        title="Family"
        subtitle={isElder ? "You decide who can see your accounts and approve actions." : `${elder?.display_name ?? "The account owner"} decides what you can see and do.`}
      />
      <div className="space-y-4">
        {household.members.map((m) => (
          <Card key={m.id}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-lg text-white">
                  {m.display_name} {m.is_me && <span className="text-white/40">(you)</span>}
                </p>
                <p className="text-sm text-white/45">{m.email}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>{m.role === "elder" ? "Account owner" : "Approver"}</Badge>
                {m.status === "invited" && <Badge tone="amber">Invited</Badge>}
                {m.role === "approver" && m.status === "active" && m.scopes.length === 0 && <Badge tone="amber">No access yet</Badge>}
              </div>
            </div>
            {m.role === "approver" && m.scopes.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm text-white/65">
                {m.scopes.map((s) => (
                  <li key={s}>✓ {SCOPE_TEXT[s].title}</li>
                ))}
              </ul>
            )}
            {isElder && m.role === "approver" && <ConsentEditor household={household} approver={m} onSaved={() => void refreshHouseholds()} />}
          </Card>
        ))}

        {!isElder && approvers.some((a) => a.is_me && a.scopes.length === 0) && (
          <Notice>
            {elder?.status === "invited"
              ? `${elder.display_name} hasn't accepted the invite yet. Once they do, they choose what to share with you.`
              : `${elder?.display_name ?? "The account owner"} hasn't chosen what to share yet. They do it from this page on their side.`}
          </Notice>
        )}

        <Card>
          <p className="mb-4 text-lg text-white">{inviteRole === "elder" ? "Invite the account owner" : "Invite a family approver"}</p>
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={async (e) => {
              e.preventDefault();
              setError(null);
              try {
                setInviteResult(await api<InviteResult>(`/households/${household.id}/members`, { body: { ...invite, role: inviteRole } }));
                setInvite({ email: "", display_name: "" });
                void refreshHouseholds();
              } catch (err) {
                setError(err instanceof Error ? err.message : "Couldn't send the invite.");
              }
            }}
          >
            <Field label="Their name">
              <input required className={inputClass} value={invite.display_name} onChange={(e) => setInvite({ ...invite, display_name: e.target.value })} />
            </Field>
            <Field label="Their email">
              <input required type="email" className={inputClass} value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            </Field>
            <div>
              <Button type="submit" variant="secondary">
                Send invite
              </Button>
            </div>
          </form>
          {inviteResult && (
            <div className="mt-4">
              {inviteResult.emailed ? (
                <Notice>Invite emailed to {inviteResult.member.email}.</Notice>
              ) : (
                <Notice tone="amber">
                  Email isn&apos;t set up on this server, so send this link yourself (text or WhatsApp is fine):
                  <span className="mt-2 block select-all break-all font-mono text-sm text-white">{inviteResult.invite_link}</span>
                </Notice>
              )}
            </div>
          )}
          {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
        </Card>
      </div>
    </Page>
  );
}
