"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Button, Field, Notice, ShieldIcon, inputClass } from "@/components/ui";
import { API_URL } from "@/lib/api";
import { setDevEmail } from "@/lib/auth";
import { supabase } from "@/lib/supabaseClient";

type Step = "email" | "code";

function LoginForm() {
  const params = useSearchParams();
  const next = params.get("next") || "/chat";
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState(params.get("email") || "");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devAuth, setDevAuth] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/integrations`)
      .then((r) => r.json())
      .then((d) => setDevAuth(Boolean(d.dev_auth)))
      .catch(() => setDevAuth(false));
  }, []);

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    // Passwordless: one code by email, which also creates the account on
    // first sign-in. Nothing to remember, nothing to reset.
    const { error: otpError } = await supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
    setLoading(false);
    if (otpError) setError("We couldn't send the code. Check the email address and try again.");
    else setStep("code");
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error: verifyError } = await supabase.auth.verifyOtp({ email, token: code.trim(), type: "email" });
    setLoading(false);
    if (verifyError) setError("That code is wrong or has expired. Try again, or ask for a new one.");
    else {
      setDevEmail(null);
      window.location.href = next;
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        <ShieldIcon className="h-8 w-8 text-white" />
        <h1 className="mt-6 text-3xl font-semibold tracking-tight text-white">
          {step === "email" ? "Sign in to Warden" : "Check your email"}
        </h1>

        {step === "email" && (
          <form onSubmit={sendCode} className="mt-8 space-y-4">
            <Field label="Email">
              <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
            </Field>
            {error && <p className="text-sm text-red-300">{error}</p>}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Sending…" : "Email me a code"}
            </Button>
            <p className="text-sm text-white/45">No password. We send a one-time code each time you sign in.</p>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={verify} className="mt-8 space-y-4">
            <p className="text-white/65">
              We sent a code to <span className="text-white">{email}</span>. Type it here.
            </p>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              aria-label="Code"
              className={`${inputClass} text-center text-2xl tracking-[0.4em]`}
            />
            {error && <p className="text-sm text-red-300">{error}</p>}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Checking…" : "Sign in"}
            </Button>
            <button type="button" onClick={() => setStep("email")} className="w-full text-sm text-white/55 hover:text-white">
              Use a different email
            </button>
          </form>
        )}

        {devAuth && (
          <div className="mt-10 space-y-3">
            <Notice tone="amber">
              Development login is on (this API runs with DEV_AUTH_ENABLED). It signs in as any email without a code — never
              available in production.
            </Notice>
            <Button
              variant="secondary"
              className="w-full"
              disabled={!email}
              onClick={() => {
                setDevEmail(email);
                window.location.href = next;
              }}
            >
              Dev sign-in as {email || "…"}
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
