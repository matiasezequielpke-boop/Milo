"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Notice, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

function Unsubscribe() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "done" | "error">("working");
  const [error, setError] = useState<string | null>(null);

  // One step, no "are you sure": the link in the email is the request.
  useEffect(() => {
    if (!token) {
      setState("error");
      setError("This unsubscribe link is missing its code.");
      return;
    }
    api(`/email/unsubscribe?token=${encodeURIComponent(token)}`, { method: "POST" })
      .then(() => setState("done"))
      .catch((e) => {
        setState("error");
        setError(e instanceof Error ? e.message : "Couldn't unsubscribe you.");
      });
  }, [token]);

  return (
    <div className="authcard glass deep">
      <h1>Notification emails</h1>
      {state === "working" && <Spinner label="Turning them off" />}
      {state === "done" && (
        <>
          <p className="sub">
            Done — Warden won&apos;t email you about approvals, alerts or results anymore. You&apos;ll still see them in the app, and
            sign-in codes still arrive when you log in.
          </p>
          <p className="alt">
            Changed your mind? Turn them back on in <Link href="/settings">Settings</Link>.
          </p>
        </>
      )}
      {state === "error" && <Notice tone="err">{error} You can also turn emails off in Settings after logging in.</Notice>}
    </div>
  );
}

export default function UnsubscribePage() {
  return (
    <Suspense>
      <Unsubscribe />
    </Suspense>
  );
}
