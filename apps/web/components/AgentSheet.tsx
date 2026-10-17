"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { IconCheck, IconClock } from "@/components/icons";
import { Toy } from "@/components/Toy";
import { agentById } from "@/lib/agents";
import { useApp } from "@/lib/store";

/** Agent details. Enters from the right and leaves the same way it came
 *  (materializes: blur + scale + slide). Stats are live counts or plain
 *  "not connected" — never invented numbers. */
export function AgentSheet({ agentId, onClose }: { agentId: string | null; onClose: () => void }) {
  const router = useRouter();
  const app = useApp();
  const closeBtn = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const open = agentId !== null;
  // Keep showing the last agent while the sheet animates out.
  const shown = useRef(agentId);
  if (agentId) shown.current = agentId;
  const a = agentById(shown.current);
  const ready = app.status === "ready";

  useEffect(() => {
    if (!open) return;
    returnTo.current = document.activeElement as HTMLElement | null;
    const t = setTimeout(() => closeBtn.current?.focus(), 30);
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
      // Keep Tab inside the open sheet (it's modal).
      if (e.key === "Tab" && sheetRef.current) {
        const items = sheetRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]");
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", esc);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", esc);
      returnTo.current?.focus?.();
    };
  }, [open]);

  const i = app.integrations;
  const stats: [string, string][] = !a.live
    ? []
    : !ready
      ? [["Connection", "Not connected"]]
      : a.id === "milo"
        ? [
            ["Model", i?.model ? i.model_id : "Not connected"],
            ["Your chats", String(app.conversations.length)],
          ]
        : a.id === "warden"
          ? [
              ["Waiting for approval", String(app.pendingApprovals)],
              ["Payments", i?.stripe ? (i.stripe_mode === "live" ? "Stripe (live)" : "Stripe test mode") : "Not connected"],
            ]
          : [
              ["Open alerts", String(app.openAlerts)],
              ["Bank data", i?.plaid ? `Plaid ${i.plaid_env}` : "Not connected"],
            ];
  const state = !a.live ? "Coming soon" : !ready ? "Offline" : a.id === "milo" && !i?.model ? "Waiting for model key" : "Ready";
  const stateColor = state === "Ready" ? "var(--live)" : a.live ? "var(--busy)" : "var(--ink-3)";

  const action =
    a.id === "milo"
      ? { label: "Chat with Milo", go: () => (app.setConversation(null), router.push("/")) }
      : a.id === "warden"
        ? { label: "Open approvals", go: () => router.push("/approvals") }
        : a.id === "sentinel"
          ? { label: "Open alerts", go: () => router.push("/alerts") }
          : null;

  return (
    <>
      <div className={`veil ${open ? "on" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside
        ref={sheetRef}
        className={`sheet glass deep ${open ? "on" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
        aria-labelledby="sheet-title"
      >
        <div className="sh">
          <Toy kind={a.kind} />
          <div>
            <b id="sheet-title">{a.name}</b>
            <span>{a.role}</span>
          </div>
          <button className="x" ref={closeBtn} onClick={onClose} aria-label="Close" tabIndex={open ? 0 : -1}>
            ✕
          </button>
        </div>
        <div className="sb">
          <div className="hero">
            <Toy kind={a.kind} label={`${a.name}, drawn as a small plush character`} />
          </div>
          <p className="about">{a.about}</p>
          <h4>Status</h4>
          <div className="kv">
            <span>State</span>
            <span style={{ color: stateColor }}>{state}</span>
          </div>
          {stats.map(([k, v]) => (
            <div className="kv" key={k}>
              <span>{k}</span>
              <span className="mono">{v}</span>
            </div>
          ))}
          <h4>{a.live ? "What it does" : "What it will do"}</h4>
          <ul className={`cl ${a.live ? "" : "soon"}`}>
            {a.does.map((d) => (
              <li key={d}>
                {a.live ? <IconCheck /> : <IconClock />}
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="sf">
          <button className="bt g" onClick={onClose} tabIndex={open ? 0 : -1}>
            Close
          </button>
          {action && (
            <button
              className="bt p"
              tabIndex={open ? 0 : -1}
              onClick={() => {
                onClose();
                action.go();
              }}
            >
              {action.label}
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
