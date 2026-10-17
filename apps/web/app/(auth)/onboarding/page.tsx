"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { InviteResult } from "@/lib/types";

type Role = "elder" | "approver";

/** First run for a new account: who are you in this, and who's the other
 *  person. The account owner always decides what a family approver can
 *  see — nothing is shared until they say so. */
export default function OnboardingPage() {
  const router = useRouter();
  const { status, mode, households, me, refreshHouseholds } = useApp();
  const [role, setRole] = useState<Role>("elder");
  const [myName, setMyName] = useState("");
  const [other, setOther] = useState({ name: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState<InviteResult | null>(null);

  useEffect(() => {
    if (status === "signed-out") router.replace("/login?next=/onboarding");
    if (status === "ready" && (mode === "demo" || (households.length > 0 && !invite))) router.replace("/");
  }, [status, mode, households.length, invite, router]);

  if (invite) {
    return (
      <div className="authcard glass deep">
        <h1>You&apos;re set up</h1>
        {invite.emailed ? (
          <p className="sub">We emailed an invite to {invite.member.email}.</p>
        ) : (
          <>
            <p className="sub">Email isn&apos;t set up on this server, so send {invite.member.display_name} this link yourself:</p>
            <p className="code" style={{ fontSize: 13, letterSpacing: 0, wordBreak: "break-all", userSelect: "all", margin: "0 0 16px" }}>
              {invite.invite_link}
            </p>
          </>
        )}
        <button className="bt p" onClick={() => router.replace("/")}>
          Go to Warden
        </button>
      </div>
    );
  }

  const elderName = role === "elder" ? myName : other.name;
  return (
    <div className="authcard glass deep">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const result = await api<{ invite: InviteResult | null }>("/households", {
              body: {
                name: `${elderName.trim() || "My"}'s accounts`,
                my_role: role,
                my_display_name: myName.trim(),
                invite: other.email.trim()
                  ? { email: other.email.trim(), display_name: other.name.trim() || other.email.split("@")[0], role: role === "elder" ? "approver" : "elder" }
                  : null,
              },
            });
            // Show the invite result before the household list updates, or the
            // "already set up" redirect would skip it.
            if (result.invite) setInvite(result.invite);
            await refreshHouseholds();
            if (!result.invite) router.replace("/");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Couldn't set this up.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <h1>Set up Warden</h1>
        <p className="sub">Signed in as {me?.email}. Two quick questions.</p>
        {error && <Notice tone="err">{error}</Notice>}
        <fieldset className="choice" style={{ border: 0, padding: 0, margin: "0 0 16px" }}>
          <legend className="fl" style={{ padding: 0, marginBottom: 8, fontSize: 12.5, color: "var(--ink-3)", fontWeight: 500 }}>
            Whose accounts will Warden watch?
          </legend>
          <label>
            <input type="radio" name="role" checked={role === "elder"} onChange={() => setRole("elder")} />
            <span>
              <b>Mine</b>
              <span>I&apos;ll connect my bank and choose which family member can approve payments.</span>
            </span>
          </label>
          <label>
            <input type="radio" name="role" checked={role === "approver"} onChange={() => setRole("approver")} />
            <span>
              <b>A parent&apos;s or relative&apos;s</b>
              <span>I&apos;m helping someone. They join, connect their bank and decide what I can see.</span>
            </span>
          </label>
        </fieldset>
        <label className="fl">
          <span>Your name</span>
          <input required maxLength={120} autoComplete="given-name" value={myName} onChange={(e) => setMyName(e.target.value)} />
        </label>
        <label className="fl">
          <span>{role === "elder" ? "Family member who'll approve payments (optional)" : "Their name"}</span>
          <input required={role === "approver"} maxLength={120} value={other.name} onChange={(e) => setOther({ ...other, name: e.target.value })} />
        </label>
        <label className="fl">
          <span>{role === "elder" ? "Their email (optional — you can invite later)" : "Their email"}</span>
          <input type="email" required={role === "approver"} value={other.email} onChange={(e) => setOther({ ...other, email: e.target.value })} />
          <span className="hint">We only use it to send the invite. They choose whether to join.</span>
        </label>
        <button className="bt p" type="submit" disabled={busy}>
          {busy ? "Setting up…" : "Continue"}
        </button>
      </form>
    </div>
  );
}
