"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { PasswordField, safeNext } from "@/components/AuthBits";
import { Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { SessionResponse } from "@/lib/types";

type Step = "password" | "code";

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const { status, integrations, signIn, enterDemo } = useApp();
  const [step, setStep] = useState<Step>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(params.get("deleted") ? "Your account was deleted." : null);
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);

  // Already signed in (or exploring the demo) → straight in.
  useEffect(() => {
    if (status === "ready") router.replace(next);
  }, [status, next, router]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const offline = status === "offline" || status === "unreachable";
  const authOff = integrations && !integrations.auth;

  return (
    <div className="authcard glass deep">
      {step === "password" ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api("/auth/login", { body: { email, password } });
              setPassword("");
              setStep("code");
              setInfo(null);
              setCooldown(60);
              setTimeout(() => codeRef.current?.focus(), 50);
            });
          }}
        >
          <h1>Log in</h1>
          <p className="sub">Enter your email and password. We&apos;ll then email you a code to finish signing in.</p>
          {info && <Notice>{info}</Notice>}
          {offline && <Notice tone="warn">Warden&apos;s server isn&apos;t reachable from this site right now, so logging in won&apos;t work yet.</Notice>}
          {authOff && <Notice tone="warn">Sign-in isn&apos;t set up on this server yet.</Notice>}
          {error && <Notice tone="err">{error}</Notice>}
          <label className="fl">
            <span>Email</span>
            <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <PasswordField value={password} onChange={setPassword} autoComplete="current-password" />
          <button className="bt p" type="submit" disabled={busy}>
            {busy ? "Checking…" : "Continue"}
          </button>
          <p className="alt">
            New to Warden? <Link href={`/signup${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`}>Create an account</Link>
          </p>
          {integrations?.demo_mode && (
            <p className="alt">
              Just looking?{" "}
              <button
                type="button"
                className="link"
                style={{ color: "var(--accent)", textDecoration: "underline", textUnderlineOffset: 3 }}
                onClick={() =>
                  void run(async () => {
                    await enterDemo();
                    router.replace("/");
                  })
                }
              >
                Explore the demo family
              </button>
            </p>
          )}
        </form>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const session = await api<SessionResponse>("/auth/login/verify", { body: { email, code: code.trim() } });
              await signIn({
                access_token: session.access_token,
                refresh_token: session.refresh_token,
                expires_at: session.expires_at,
                email: session.user.email,
              });
              router.replace(next);
            });
          }}
        >
          <h1>Check your email</h1>
          <p className="sub">
            We sent a sign-in code to <b>{email}</b>. It expires in 10 minutes.
          </p>
          {info && <Notice>{info}</Notice>}
          {error && <Notice tone="err">{error}</Notice>}
          <label className="fl">
            <span>Code</span>
            <input
              ref={codeRef}
              className="code"
              required
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6,10}"
              maxLength={10}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
          </label>
          <button className="bt p" type="submit" disabled={busy || code.length < 6}>
            {busy ? "Checking…" : "Log in"}
          </button>
          <p className="alt">
            No email?{" "}
            {cooldown > 0 ? (
              <span>You can ask for another code in {cooldown}s.</span>
            ) : (
              <button
                type="button"
                style={{ color: "var(--accent)", textDecoration: "underline", textUnderlineOffset: 3 }}
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api("/auth/login/resend", { body: { email } });
                    setInfo("We sent a new code. Use the most recent one.");
                    setCooldown(60);
                  })
                }
              >
                Send a new code
              </button>
            )}{" "}
            · Check your spam folder too.
          </p>
          <p className="alt">
            <button
              type="button"
              style={{ color: "var(--accent)", textDecoration: "underline", textUnderlineOffset: 3 }}
              onClick={() => {
                setStep("password");
                setCode("");
                setError(null);
                setInfo(null);
              }}
            >
              Use a different email
            </button>
          </p>
        </form>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}
