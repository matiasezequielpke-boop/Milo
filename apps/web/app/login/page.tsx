"use client";

import { useState } from "react";
import { supabase, SUPABASE_URL, SUPABASE_ANON_KEY } from "@/lib/supabaseClient";

type Step = "credentials" | "code" | "done";

export default function LoginPage() {
  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCredentials(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${SUPABASE_URL}/functions/v1/login-start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(
          data?.error === "invalid_credentials"
            ? "Correo o contraseña incorrectos."
            : "No se pudo iniciar el acceso. Intenta de nuevo."
        );
        return;
      }
      setStep("code");
    } catch {
      setError("No se pudo conectar. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { error: verifyError } = await supabase.auth.verifyOtp({
        email,
        token: code,
        type: "email",
      });
      if (verifyError) {
        setError("Código incorrecto o expirado.");
        return;
      }
      setStep("done");
    } catch {
      setError("No se pudo verificar el código. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-ink-950 px-6 py-16 flex items-center justify-center">
      <div className="w-full max-w-sm glass p-8">
        <p className="mb-2 text-sm uppercase tracking-widest text-terracotta-400">Milo</p>
        <h1 className="mb-6 text-2xl font-semibold text-white">
          {step === "credentials" && "Iniciar sesión"}
          {step === "code" && "Revisa tu correo"}
          {step === "done" && "Sesión iniciada"}
        </h1>

        {step === "credentials" && (
          <form onSubmit={handleCredentials} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-white/40">
                Correo
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none focus:border-terracotta-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-white/40">
                Contraseña
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-white outline-none focus:border-terracotta-400"
              />
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-terracotta-500 px-5 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-terracotta-400 disabled:opacity-50"
            >
              {loading ? "Comprobando…" : "Continuar"}
            </button>
            <p className="text-xs text-white/40">
              Por ahora enviamos un código de un solo uso a tu correo — todavía no hay
              recuperación de contraseña ni verificación por SMS.
            </p>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={handleCode} className="space-y-4">
            <p className="text-sm text-white/60">
              Te enviamos un código a <span className="text-white">{email}</span>. Escríbelo
              para entrar.
            </p>
            <input
              type="text"
              inputMode="numeric"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-center text-lg tracking-widest text-white outline-none focus:border-terracotta-400"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-terracotta-500 px-5 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-terracotta-400 disabled:opacity-50"
            >
              {loading ? "Verificando…" : "Entrar"}
            </button>
          </form>
        )}

        {step === "done" && (
          <p className="text-sm text-white/70">
            Listo — ya tienes una sesión válida guardada en el navegador.
          </p>
        )}
      </div>
    </main>
  );
}
