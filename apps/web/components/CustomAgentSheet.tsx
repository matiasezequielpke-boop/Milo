"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type RefObject } from "react";

import { IconCheck, IconClock, IconEdit, IconInfo, IconLock, IconPlay, IconTrash } from "@/components/icons";
import { Toy, type ToyKind } from "@/components/Toy";
import { Notice } from "@/components/ui";
import { AGENT_TEMPLATES, CUSTOM_KINDS, RESERVED_NAMES, SCHEDULES, scheduleShort } from "@/lib/agents";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { AgentSchedule, CustomAgent } from "@/lib/types";

const FACE_NAME: Record<string, string> = {
  blob: "Round",
  lens: "Magnifier",
  envelope: "Envelope",
  calc: "Calculator",
  paper: "Paper",
  parcel: "Parcel",
  mug: "Mug",
  stamp: "Stamp",
};

export function SheetHead({
  kind,
  own = true,
  title,
  sub,
  closeRef,
  onClose,
}: {
  kind: ToyKind;
  own?: boolean;
  title: string;
  sub: string;
  closeRef: RefObject<HTMLButtonElement>;
  onClose: () => void;
}) {
  return (
    <div className="sh">
      <Toy kind={kind} own={own} />
      <div>
        <b id="sheet-title">{title}</b>
        <span>{sub}</span>
      </div>
      <button className="x" ref={closeRef} onClick={onClose} aria-label="Close">
        ✕
      </button>
    </div>
  );
}

/** Make a new agent, or change one. The face, name, job and schedule are
 *  all there is: what it may do is fixed (read-only) and said up front. */
export function AgentForm({
  agent,
  closeRef,
  onClose,
  onCancel,
  onSaved,
}: {
  agent?: CustomAgent;
  closeRef: RefObject<HTMLButtonElement>;
  onClose: () => void;
  onCancel: () => void;
  onSaved: (agent: CustomAgent) => void;
}) {
  const household = useActiveHousehold();
  const emails = useApp((s) => Boolean(s.integrations?.email));
  const [name, setName] = useState(agent?.name ?? "");
  const [instructions, setInstructions] = useState(agent?.instructions ?? "");
  const [kind, setKind] = useState<ToyKind>(agent?.kind ?? "blob");
  const [schedule, setSchedule] = useState<AgentSchedule>(agent?.schedule ?? "manual");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canRead = Boolean(household?.my_scopes.includes("view_accounts"));
  const owner = household?.members.find((m) => m.role === "elder")?.display_name || "The account owner";
  const taken = RESERVED_NAMES.includes(name.trim().toLowerCase());
  const valid = name.trim().length > 0 && instructions.trim().length >= 10 && !taken;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!household || !valid || busy) return;
    setBusy(true);
    setError(null);
    const body = { name: name.trim(), instructions: instructions.trim(), kind, schedule };
    try {
      const saved = agent
        ? await api<CustomAgent>(`/households/${household.id}/agents/${agent.id}`, { method: "PATCH", body })
        : await api<CustomAgent>(`/households/${household.id}/agents`, { body });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save the agent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <SheetHead
        kind={kind}
        title={agent ? `Edit ${agent.name}` : "New agent"}
        sub="One job · read-only"
        closeRef={closeRef}
        onClose={onClose}
      />
      <form id="agent-form" className="sb" onSubmit={submit} noValidate>
        <div className="hero">
          <Toy kind={kind} own label={`${name.trim() || "Your agent"}, drawn as a small plush character`} />
        </div>
        {!agent && (
          <div className="tpl">
            <span id="tpl-h">Start from an example</span>
            <div role="group" aria-labelledby="tpl-h">
              {AGENT_TEMPLATES.map((t) => (
                <button
                  type="button"
                  key={t.name}
                  className="sug"
                  onClick={() => {
                    setName(t.name);
                    setInstructions(t.instructions);
                    setKind(t.kind);
                    setSchedule(t.schedule);
                  }}
                >
                  {t.name}
                </button>
              ))}
            </div>
          </div>
        )}
        {!canRead && (
          <Notice tone="warn">
            {owner} hasn&apos;t shared the accounts with you yet, so an agent would have nothing to read. They can allow it on the Family page.
          </Notice>
        )}
        <label className="fl">
          <span>Name</span>
          <input
            data-autofocus
            value={name}
            maxLength={40}
            placeholder="e.g. Spending review"
            aria-invalid={taken}
            aria-describedby={taken ? "name-taken" : undefined}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        {taken && (
          <p className="fhint err" id="name-taken">
            That&apos;s one of Warden&apos;s own agents. Pick another name.
          </p>
        )}
        <label className="fl">
          <span>What should it do?</span>
          <textarea
            rows={5}
            value={instructions}
            maxLength={2000}
            placeholder="Write it the way you'd ask a person. For example: tell me where the money went this month, and anything that looks off."
            aria-describedby="job-hint"
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>
        <p className="fhint" id="job-hint">
          {instructions.trim().length < 10 ? "A sentence or two is enough." : `${instructions.length} / 2000`}
        </p>
        <fieldset className="faces">
          <legend>Face</legend>
          {CUSTOM_KINDS.map((k) => (
            <label key={k} className={kind === k ? "on" : ""}>
              <input type="radio" name="agent-face" value={k} checked={kind === k} onChange={() => setKind(k)} />
              <Toy kind={k} own label={FACE_NAME[k]} />
            </label>
          ))}
        </fieldset>
        <label className="fl">
          <span>When it runs</span>
          <select value={schedule} onChange={(e) => setSchedule(e.target.value as AgentSchedule)}>
            {SCHEDULES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <ul className="cl notes">
          <li>
            <IconLock />
            <span>Read-only: it reads the accounts, bills, alerts and subscriptions. It can&apos;t pay, cancel or ask the family for approvals.</span>
          </li>
          {schedule !== "manual" && (
            <li>
              <IconClock />
              <span>
                Runs at 13:00 UTC (morning in the US). The report lands in your chats{emails ? " and Warden emails you when it's ready" : ""}.
              </span>
            </li>
          )}
          <li>
            <IconInfo />
            <span>Everyone in the family can see this agent and its job.</span>
          </li>
        </ul>
        {error && <Notice tone="err">{error}</Notice>}
      </form>
      <div className="sf">
        <button className="bt g" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="bt p" type="submit" form="agent-form" disabled={!valid || busy || !canRead}>
          {busy ? "Saving…" : agent ? "Save" : "Make agent"}
        </button>
      </div>
    </>
  );
}

/** One agent the family made: its job, when it runs, and what it can't do.
 *  The person who made it (or the account owner) can change or delete it. */
export function CustomAgentView({
  agent,
  closeRef,
  onClose,
  onEdit,
}: {
  agent: CustomAgent;
  closeRef: RefObject<HTMLButtonElement>;
  onClose: () => void;
  onEdit: () => void;
}) {
  const router = useRouter();
  const app = useApp();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const modelReady = app.status === "ready" && Boolean(app.integrations?.model);

  function chat(runNow: boolean) {
    onClose();
    app.startAgentChat(agent.ref, runNow);
    router.push("/");
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api(`/households/${agent.household_id}/agents/${agent.id}`, { method: "DELETE" });
      onClose();
      if (useApp.getState().chatAgent === agent.ref) app.setConversation(null);
      await app.refreshAgents();
      app.showToast(`${agent.name} was deleted`, agent.kind, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't delete the agent.");
      setBusy(false);
    }
  }

  return (
    <>
      <SheetHead
        kind={agent.kind}
        title={agent.name}
        sub={agent.created_by ? `Made by ${agent.created_by}` : "Made by your family"}
        closeRef={closeRef}
        onClose={onClose}
      />
      <div className="sb">
        <div className="hero">
          <Toy kind={agent.kind} own label={`${agent.name}, drawn as a small plush character`} />
        </div>
        <h4>Its job</h4>
        <p className="job">{agent.instructions}</p>
        <h4>Runs</h4>
        <div className="kv">
          <span>Schedule</span>
          <span>{scheduleShort(agent.schedule)}</span>
        </div>
        {agent.next_run_at && (
          <div className="kv">
            <span>Next run</span>
            <span>{when(agent.next_run_at)}</span>
          </div>
        )}
        {agent.schedule !== "manual" && (
          <div className="kv">
            <span>Last scheduled run</span>
            <span>{agent.last_run_at ? when(agent.last_run_at) : "Not yet"}</span>
          </div>
        )}
        <h4>What it can do</h4>
        <ul className="cl">
          <li>
            <IconCheck />
            <span>Reads the accounts, transactions, bills, alerts and subscriptions</span>
          </li>
          <li>
            <IconCheck />
            <span>Reports back: the headline, the key numbers, anything unusual</span>
          </li>
          <li className="no">
            <IconLock />
            <span>Can&apos;t pay, cancel or ask for approvals. Only Warden does that, and only with the family&apos;s yes.</span>
          </li>
        </ul>
        {agent.can_edit && (
          <>
            <h4>Manage</h4>
            {confirming ? (
              <div className="confirm">
                <p>
                  Delete <b>{agent.name}</b>? Its past chats stay, but it won&apos;t answer or run again. This can&apos;t be undone.
                </p>
                <div>
                  <button className="bt g sm" autoFocus onClick={() => setConfirming(false)} disabled={busy}>
                    Keep it
                  </button>
                  <button className="bt x sm" onClick={remove} disabled={busy}>
                    {busy ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mrow">
                <button className="bt g sm" onClick={onEdit}>
                  <IconEdit />
                  Edit
                </button>
                <button className="bt x sm" onClick={() => setConfirming(true)}>
                  <IconTrash />
                  Delete
                </button>
              </div>
            )}
          </>
        )}
        {error && <Notice tone="err">{error}</Notice>}
      </div>
      <div className="sf">
        <button
          className="bt g"
          onClick={() => chat(true)}
          disabled={!modelReady}
          title={modelReady ? "Start its job now; the report appears in a new chat" : "The model isn't connected on this server yet"}
        >
          <IconPlay />
          Run now
        </button>
        <button className="bt p" onClick={() => chat(false)}>
          Chat
        </button>
      </div>
    </>
  );
}
