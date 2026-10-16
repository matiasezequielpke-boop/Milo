"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Field, Notice, ShieldIcon, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { Household, InviteResult } from "@/lib/types";

export default function OnboardingPage() {
  const router = useRouter();
  const refreshHouseholds = useApp((s) => s.refreshHouseholds);
  const setActive = useApp((s) => s.setActive);
  const [mode, setMode] = useState<"parent" | "self" | null>(null);
  const [me, setMe] = useState("");
  const [other, setOther] = useState({ name: "", email: "" });
  const [result, setResult] = useState<{ household: Household; invite: InviteResult | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const forParent = mode === "parent";
      const ownerName = forParent ? other.name : me;
      const res = await api<{ household: Household; invite: InviteResult | null }>("/households", {
        body: {
          name: `${ownerName}'s accounts`,
          my_role: forParent ? "approver" : "elder",
          my_display_name: me,
          invite: other.email ? { email: other.email, display_name: other.name, role: forParent ? "elder" : "approver" } : null,
        },
      });
      await refreshHouseholds();
      setActive(res.household.id);
      if (res.invite && !res.invite.emailed) setResult(res);
      else router.push(forParent ? "/family" : "/accounts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't set that up.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-12 sm:py-20">
      <ShieldIcon className="h-8 w-8 text-white" />
      <h1 className="mt-6 text-3xl font-semibold tracking-tight text-white">Set up Warden</h1>
      <p className="mt-3 text-white/60">
        Warden watches an account for scams and odd charges, and never pays or cancels anything without a family
        member&apos;s OK.
      </p>

      {result ? (
        <div className="mt-10 space-y-4">
          <Notice tone="amber">
            Email isn&apos;t set up on this server, so send {result.invite?.member.display_name} this link yourself:
            <span className="mt-2 block select-all break-all font-mono text-sm text-white">{result.invite?.invite_link}</span>
          </Notice>
          <Button onClick={() => router.push(mode === "parent" ? "/family" : "/accounts")}>Continue</Button>
        </div>
      ) : !mode ? (
        <div className="mt-10 grid gap-3">
          <button onClick={() => setMode("parent")} className="rounded-2xl border border-white/15 p-5 text-left hover:border-white/40">
            <span className="block text-lg text-white">For my parent (or another relative)</span>
            <span className="mt-1 block text-white/55">I&apos;ll approve payments; they keep control of what&apos;s shared.</span>
          </button>
          <button onClick={() => setMode("self")} className="rounded-2xl border border-white/15 p-5 text-left hover:border-white/40">
            <span className="block text-lg text-white">For my own accounts</span>
            <span className="mt-1 block text-white/55">I&apos;ll invite someone I trust to approve payments.</span>
          </button>
        </div>
      ) : (
        <form onSubmit={create} className="mt-10 space-y-4">
          <Field label="Your first name">
            <input required className={inputClass} value={me} onChange={(e) => setMe(e.target.value)} />
          </Field>
          <Field label={mode === "parent" ? "Their name" : "Your approver's name"} hint={mode === "parent" ? "e.g. Mom, or Rosa" : undefined}>
            <input required className={inputClass} value={other.name} onChange={(e) => setOther({ ...other, name: e.target.value })} />
          </Field>
          <Field
            label={mode === "parent" ? "Their email" : "Your approver's email"}
            hint={mode === "parent" ? "They'll get an invite and decide what to share. Nothing is shared until they do." : undefined}
          >
            <input required type="email" className={inputClass} value={other.email} onChange={(e) => setOther({ ...other, email: e.target.value })} />
          </Field>
          {error && <p className="text-sm text-red-300">{error}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Setting up…" : "Continue"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              Back
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
