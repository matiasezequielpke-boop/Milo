import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-white text-black hover:bg-white/85",
  secondary: "border border-white/20 text-white hover:bg-white/10",
  danger: "border border-red-500/60 text-red-300 hover:bg-red-500/10",
  ghost: "text-white/70 hover:text-white hover:bg-white/5",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2 text-[0.95rem] font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
    />
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-white/10 bg-ink-900 p-5 ${className}`}>{children}</div>;
}

export function PageTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 text-white/55">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "red" | "amber" | "green"; children: ReactNode }) {
  const tones = {
    neutral: "border-white/15 text-white/70",
    red: "border-red-500/50 text-red-300",
    amber: "border-amber-400/50 text-amber-200",
    green: "border-emerald-500/50 text-emerald-300",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Empty({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/15 px-6 py-10 text-center">
      <p className="text-lg text-white">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-md text-white/55">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "neutral", children }: { tone?: "neutral" | "red" | "amber"; children: ReactNode }) {
  const tones = {
    neutral: "border-white/15 bg-white/[0.03] text-white/75",
    red: "border-red-500/40 bg-red-500/[0.06] text-red-200",
    amber: "border-amber-400/40 bg-amber-400/[0.06] text-amber-100",
  };
  return <div className={`rounded-xl border px-4 py-3 text-[0.95rem] ${tones[tone]}`}>{children}</div>;
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm text-white/60">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-white/40">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-xl border border-white/15 bg-black px-4 py-3 text-white placeholder:text-white/30 outline-none focus:border-white/60";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 text-white/50">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white" />
      {label}
    </div>
  );
}

export function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="underline decoration-white/30 underline-offset-4 hover:decoration-white">
      {children}
    </Link>
  );
}

export function ShieldIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className} aria-hidden>
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" strokeLinejoin="round" />
    </svg>
  );
}
