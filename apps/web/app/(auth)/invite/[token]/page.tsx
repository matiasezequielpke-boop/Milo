"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Notice, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";

type Preview = { household_name: string; invited_email: string; display_name: string; role: "elder" | "approver" };

export default function InvitePage({ params }: { params: { token: string } }) {
  const router = useRouter();
  const { status, mode, me, refreshHouseholds } = useApp();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const here = `/invite/${params.token}`;

  useEffect(() => {
    if (status === "loading" || status === "offline") return;
    api<Preview>(`/households/invites/${encodeURIComponent(params.token)}`)
      .then(setPreview)
      .catch((e) => setError(e instanceof Error ? e.message : "This invite link isn't valid."));
  }, [params.token, status]);

  const signedIn = status === "ready" && mode === "user";
  return (
    <div className="authcard glass deep">
      <h1>You&apos;re invited</h1>
      {!preview && !error && <Spinner />}
      {error && <Notice tone="err">{error}</Notice>}
      {preview && (
        <>
          <p className="sub">
            Join <b>{preview.household_name}</b> on Warden as {preview.role === "elder" ? "the account owner" : "a family approver"}.
            {preview.role === "approver"
              ? " You'll only see what the account owner chooses to share, and you can approve or block payments Warden prepares."
              : " You'll connect your bank and decide what your family member can see. You can change that at any time."}
          </p>
          {signedIn ? (
            <>
              {me && me.email.toLowerCase() !== preview.invited_email.toLowerCase() && (
                <Notice tone="warn">
                  This invite is for {preview.invited_email}, but you&apos;re logged in as {me.email}.
                </Notice>
              )}
              <button
                className="bt p"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    await api("/households/invites/accept", { body: { token: params.token } });
                    await refreshHouseholds();
                    router.replace("/");
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Couldn't accept the invite.");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Joining…" : "Accept invite"}
              </button>
            </>
          ) : (
            <>
              <p className="sub">
                Create an account or log in with <b>{preview.invited_email}</b> to accept.
              </p>
              <Link className="bt p" href={`/signup?next=${encodeURIComponent(here)}`}>
                Create account
              </Link>
              <p className="alt">
                Already have one? <Link href={`/login?next=${encodeURIComponent(here)}`}>Log in</Link>
              </p>
            </>
          )}
        </>
      )}
    </div>
  );
}
