"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Notice, ShieldIcon, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { SCOPE_TEXT } from "@/lib/consent";
import { useApp } from "@/lib/store";
import type { Household } from "@/lib/types";

type Preview = { household_name: string; invited_email: string; display_name: string; role: "elder" | "approver" };

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const setActive = useApp((s) => s.setActive);
  const refreshHouseholds = useApp((s) => s.refreshHouseholds);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Preview>(`/households/invites/${token}`)
      .then(setPreview)
      .catch((e) => setError(e instanceof ApiError ? e.message : "This invite couldn't be loaded."));
    getToken().then((t) => setSignedIn(Boolean(t)));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const household = await api<Household>("/households/invites/accept", { body: { token } });
      await useApp.getState().load();
      await refreshHouseholds();
      setActive(household.id);
      // The owner's first stop is deciding what to share.
      router.push(household.my_role === "elder" ? "/family" : "/chat");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't accept the invite.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-16 sm:py-24">
      <ShieldIcon className="h-8 w-8 text-white" />
      {!preview && !error && <div className="mt-8"><Spinner /></div>}
      {error && !preview && <div className="mt-8"><Notice tone="red">{error}</Notice></div>}
      {preview && (
        <>
          <h1 className="mt-6 text-3xl font-semibold tracking-tight text-white">Hi {preview.display_name}</h1>
          {preview.role === "elder" ? (
            <div className="mt-4 space-y-4 text-white/70">
              <p>
                Your family set up Warden for <span className="text-white">{preview.household_name}</span>. Warden watches
                your bank accounts for scams and unusual charges.
              </p>
              <p>
                <span className="text-white">Nothing is shared until you decide.</span> After you join, you choose exactly
                what your family can do:
              </p>
              <ul className="space-y-2">
                {Object.values(SCOPE_TEXT).map((s) => (
                  <li key={s.title} className="rounded-xl border border-white/10 p-3">
                    <span className="block text-white">{s.title}</span>
                    <span className="block text-sm text-white/55">{s.body}</span>
                  </li>
                ))}
              </ul>
              <p>Warden never pays or cancels anything without a family member&apos;s OK, and you can change your mind any time.</p>
            </div>
          ) : (
            <p className="mt-4 text-white/70">
              You&apos;ve been asked to be the family approver for <span className="text-white">{preview.household_name}</span>.
              Warden will ask you before any payment or cancellation, and alert you about suspicious charges.
            </p>
          )}
          <div className="mt-8">
            {signedIn === false ? (
              <Link
                href={`/login?next=${encodeURIComponent(`/invite/${token}`)}&email=${encodeURIComponent(preview.invited_email)}`}
                className="inline-flex min-h-11 items-center rounded-full bg-white px-6 font-medium text-black"
              >
                Sign in as {preview.invited_email}
              </Link>
            ) : (
              <Button onClick={accept} disabled={busy || signedIn === null}>
                {busy ? "Joining…" : "Join"}
              </Button>
            )}
          </div>
          {error && <div className="mt-4"><Notice tone="red">{error}</Notice></div>}
        </>
      )}
    </main>
  );
}
