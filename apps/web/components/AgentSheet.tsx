"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type RefObject } from "react";

import { AgentForm, CustomAgentView, SheetHead } from "@/components/CustomAgentSheet";
import { IconCheck, IconClock } from "@/components/icons";
import { Toy } from "@/components/Toy";
import { agentById, CUSTOM_PREFIX } from "@/lib/agents";
import { useApp } from "@/lib/store";

/** The agent sheet: one of the cast, an agent the family made
 *  ("custom:<id>"), or the form for a new one ("new"). Enters from the
 *  right and leaves the same way it came (materializes: blur + scale +
 *  slide). Stats are live counts or plain "not connected" — never invented
 *  numbers. */
export function AgentSheet({ sheetId, onClose }: { sheetId: string | null; onClose: () => void }) {
  const app = useApp();
  const closeBtn = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const open = sheetId !== null;
  // Keep showing the last content while the sheet animates out, and start
  // a fresh form each time the sheet opens.
  const shown = useRef(sheetId);
  if (sheetId) shown.current = sheetId;
  const id = shown.current;
  const wasOpen = useRef(false);
  const opened = useRef(0);
  if (open && !wasOpen.current) opened.current += 1;
  wasOpen.current = open;
  const [editing, setEditing] = useState(false);
  useEffect(() => setEditing(false), [sheetId]);

  useEffect(() => {
    if (sheetRef.current) sheetRef.current.inert = !open;
    if (!open) return;
    returnTo.current = document.activeElement as HTMLElement | null;
    const t = setTimeout(() => {
      const first = sheetRef.current?.querySelector<HTMLElement>("[data-autofocus]");
      (first ?? closeBtn.current)?.focus();
    }, 30);
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
      // Keep Tab inside the open sheet (it's modal).
      if (e.key === "Tab" && sheetRef.current) {
        const items = sheetRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), a[href], input:checked, input:not([type=radio]), textarea, select",
        );
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

  const custom = id?.startsWith(CUSTOM_PREFIX) ? app.customAgents.find((a) => a.ref === id) ?? null : null;

  let content = null;
  if (id === "new" || (custom && editing)) {
    content = (
      <AgentForm
        key={`${id}-${opened.current}`}
        agent={editing && custom ? custom : undefined}
        closeRef={closeBtn}
        onClose={onClose}
        onCancel={() => (editing ? setEditing(false) : onClose())}
        onSaved={async (saved) => {
          await app.refreshAgents();
          app.showToast(editing ? `${saved.name} was updated` : `${saved.name} is ready`, saved.kind, true);
          setEditing(false);
          app.openSheet(saved.ref);
        }}
      />
    );
  } else if (custom) {
    content = <CustomAgentView agent={custom} closeRef={closeBtn} onClose={onClose} onEdit={() => setEditing(true)} />;
  } else if (id && !id.startsWith(CUSTOM_PREFIX)) {
    content = <CastAgent agentId={id} closeRef={closeBtn} onClose={onClose} />;
  }

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
        {content}
      </aside>
    </>
  );
}

function CastAgent({ agentId, closeRef, onClose }: { agentId: string; closeRef: RefObject<HTMLButtonElement>; onClose: () => void }) {
  const router = useRouter();
  const app = useApp();
  const a = agentById(agentId);
  const ready = app.status === "ready";
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
      <SheetHead kind={a.kind} own={false} title={a.name} sub={a.role} closeRef={closeRef} onClose={onClose} />
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
        <button className="bt g" onClick={onClose}>
          Close
        </button>
        {action && (
          <button
            className="bt p"
            onClick={() => {
              onClose();
              action.go();
            }}
          >
            {action.label}
          </button>
        )}
      </div>
    </>
  );
}
