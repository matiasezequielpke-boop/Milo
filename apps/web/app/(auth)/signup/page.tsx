"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { PasswordField, safeNext } from "@/components/AuthBits";
import { Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { SessionResponse } from "@/lib/types";

function Signup() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"), "/onboarding");
  const { status, mode, signIn } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [age, setAge] = useState(false);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "ready" && mode === "user") router.replace("/");
  }, [status, mode, router]);

  return (
    <div className="authcard glass deep">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const session = await api<SessionResponse>("/auth/signup", {
              body: { email, password, accept_terms: terms, confirm_age: age },
            });
            await signIn({
              access_token: session.access_token,
              refresh_token: session.refresh_token,
              expires_at: session.expires_at,
              email: session.user.email,
            });
            router.replace(next);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Couldn't create the account.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <h1>Create your account</h1>
        <p className="sub">Free during the pilot. No card needed.</p>
        {(status === "offline" || status === "unreachable") && (
          <Notice tone="warn">Warden&apos;s server isn&apos;t reachable from this site right now, so sign-up won&apos;t work yet.</Notice>
        )}
        {error && <Notice tone="err">{error}</Notice>}
        <label className="fl">
          <span>Email</span>
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <PasswordField
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint="At least 8 characters. A short sentence you'll remember works well."
        />
        <label className="check">
          <input type="checkbox" required checked={age} onChange={(e) => setAge(e.target.checked)} />
          <span>I&apos;m 18 or older.</span>
        </label>
        <label className="check">
          <input type="checkbox" required checked={terms} onChange={(e) => setTerms(e.target.checked)} />
          <span>
            I agree to the{" "}
            <a href="/terms" target="_blank" rel="noopener">
              Terms
            </a>{" "}
            and have read the{" "}
            <a href="/privacy" target="_blank" rel="noopener">
              Privacy Policy
            </a>
            .
          </span>
        </label>
        <button className="bt p" type="submit" disabled={busy}>
          {busy ? "Creating your account…" : "Create account"}
        </button>
        <p className="alt">
          Already have an account? <Link href={`/login${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}>Log in</Link>
        </p>
      </form>
    </div>
  );
}

export default function SignupPage() {
  return (
    <Suspense>
      <Signup />
    </Suspense>
  );
}
