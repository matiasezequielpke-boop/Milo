"use client";

import type { ReactNode } from "react";

import { IconInfo, IconWarn } from "@/components/icons";
import { useApp, type Status } from "@/lib/store";

export function Notice({ tone, children }: { tone?: "warn" | "err"; children: ReactNode }) {
  return (
    <div className={`notice ${tone ?? ""}`} role={tone === "err" ? "alert" : "status"}>
      {tone ? <IconWarn /> : <IconInfo />}
      <div>{children}</div>
    </div>
  );
}

export function Empty({ title, body, children }: { title: string; body?: ReactNode; children?: ReactNode }) {
  return (
    <div className="empty">
      <b>{title}</b>
      {body}
      {children && <div className="acts">{children}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="spin" role="status">
      <i />
      {label}
    </div>
  );
}

export function Chip({ tone, children }: { tone?: "ok" | "wait" | "bad"; children: ReactNode }) {
  return (
    <span className={`chip ${tone ?? ""}`}>
      <i />
      {children}
    </span>
  );
}

const STATUS_COPY: Record<Exclude<Status, "ready">, { title: string; body: ReactNode }> = {
  loading: { title: "Connecting to Warden…", body: null },
  offline: {
    title: "Warden's API isn't connected to this site yet",
    body: "This page shows real data only — accounts, alerts and approvals appear once the API is deployed and linked. Nothing here is made up in the meantime.",
  },
  unreachable: {
    title: "Can't reach Warden right now",
    body: "The API didn't answer. Try again in a moment.",
  },
  "signed-out": {
    title: "Taking you to log in…",
    body: null,
  },
};

/** Renders children only when the app is connected; otherwise one honest
 *  sentence about why there's nothing to show. */
export function Ready({ children }: { children: ReactNode }) {
  const status = useApp((s) => s.status);
  const error = useApp((s) => s.error);
  if (status === "ready") return <>{children}</>;
  if (status === "loading") return <Spinner label="Connecting to Warden" />;
  const copy = STATUS_COPY[status];
  return (
    <Empty title={copy.title} body={<p style={{ margin: "4px auto 0", maxWidth: "52ch" }}>{status === "unreachable" && error ? error : copy.body}</p>}>
      {status === "unreachable" && (
        <button className="bt g sm" onClick={() => void useApp.getState().load()}>
          Try again
        </button>
      )}
    </Empty>
  );
}
