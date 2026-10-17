"use client";

import { useState } from "react";

/** Password field with a show/hide toggle (fewer typos, no paste blocking). */
export function PasswordField({
  value,
  onChange,
  autoComplete,
  label = "Password",
  hint,
}: {
  value: string;
  onChange: (v: string) => void;
  autoComplete: "current-password" | "new-password";
  label?: string;
  hint?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="fl">
      <span>{label}</span>
      <div className="pwrow">
        <input
          type={show ? "text" : "password"}
          required
          minLength={autoComplete === "new-password" ? 8 : 1}
          maxLength={72}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={hint ? "pw-hint" : undefined}
        />
        <button type="button" onClick={() => setShow((v) => !v)} aria-pressed={show} aria-label={show ? "Hide password" : "Show password"}>
          {show ? "Hide" : "Show"}
        </button>
      </div>
      {hint && (
        <span className="hint" id="pw-hint">
          {hint}
        </span>
      )}
    </label>
  );
}

export function safeNext(next: string | null, fallback = "/"): string {
  // Only same-site paths: never bounce someone to another domain after login.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}
