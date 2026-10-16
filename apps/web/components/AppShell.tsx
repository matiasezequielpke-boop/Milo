"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { signOut } from "@/lib/auth";
import { useActiveHousehold, useApp } from "@/lib/store";
import { ShieldIcon, Spinner } from "@/components/ui";

const NAV = [
  { href: "/chat", label: "Chat" },
  { href: "/approvals", label: "Approvals", count: "pendingApprovals" as const },
  { href: "/alerts", label: "Alerts", count: "openAlerts" as const },
  { href: "/accounts", label: "Money" },
  { href: "/family", label: "Family" },
  { href: "/activity", label: "Activity" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { status, me, households, activeId, load, setActive, pendingApprovals, openAlerts } = useApp();
  const household = useActiveHousehold();

  useEffect(() => {
    if (status === "loading") void load();
  }, [status, load]);

  useEffect(() => {
    if (status === "signed-out") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    if (status === "ready" && households.length === 0 && pathname !== "/onboarding") router.replace("/onboarding");
  }, [status, households.length, pathname, router]);

  if (status !== "ready") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  // First run: no household yet, so no navigation to show.
  if (pathname === "/onboarding" || households.length === 0) return <main>{children}</main>;

  const counts = { pendingApprovals, openAlerts };

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-white/10 md:sticky md:top-0 md:h-screen md:w-60 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-5 py-4 md:py-6">
          <Link href="/chat" className="flex items-center gap-2 text-lg font-semibold tracking-tight text-white">
            <ShieldIcon className="h-5 w-5" />
            Warden
          </Link>
          <button
            onClick={async () => {
              await signOut();
              window.location.href = "/login";
            }}
            className="text-sm text-white/50 hover:text-white md:hidden"
          >
            Sign out
          </button>
        </div>

        {households.length > 1 && (
          <div className="px-5 pb-3">
            <select
              aria-label="Household"
              value={activeId ?? ""}
              onChange={(e) => setActive(e.target.value)}
              className="w-full rounded-lg border border-white/15 bg-black px-3 py-2 text-sm text-white"
            >
              {households.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {households.length === 1 && household && (
          <p className="hidden px-5 pb-3 text-sm text-white/45 md:block">{household.name}</p>
        )}

        <nav className="scrollbar-none flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const count = item.count ? counts[item.count] : 0;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-[0.95rem] transition ${
                  active ? "bg-white/10 text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
                }`}
              >
                {item.label}
                {count > 0 && (
                  <span className="rounded-full bg-white px-2 text-xs font-semibold text-black">{count}</span>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto hidden px-5 py-5 md:block">
          <p className="truncate text-sm text-white/45">{me?.email}</p>
          <button
            onClick={async () => {
              await signOut();
              window.location.href = "/login";
            }}
            className="mt-1 text-sm text-white/60 hover:text-white"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
