"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { IconCheck, IconInfo, IconModel, IconSend, IconWarn } from "@/components/icons";
import { Markdown } from "@/components/Markdown";
import { Toy } from "@/components/Toy";
import { Notice, Spinner } from "@/components/ui";
import { customRefOf, RUN_NOW_TEXT, scheduleShort, speakerFor } from "@/lib/agents";
import { api, streamChat } from "@/lib/api";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Approval, ChatMessage, Conversation } from "@/lib/types";

type Live = { agent: string; text: string; tool: string | null; error: string | null };

function suggestions(role: "elder" | "approver" | undefined, elder: string): string[] {
  return role === "approver"
    ? [`Any suspicious charges on ${elder}'s account?`, "What's waiting for my approval?", "Which subscriptions started recently?", "What did Warden do this week?"]
    : ["Is there anything strange on my account?", "What subscriptions am I paying for?", "Please pay my electric bill", "Which bills are due soon?"];
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
  busy,
  placeholder,
  note,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
  busy: boolean;
  placeholder: string;
  note: { tone: "info" | "warn"; text: string };
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const integrations = useApp((s) => s.integrations);

  useLayoutEffect(() => {
    const ta = ref.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [value]);

  return (
    <div className="cin">
      <form
        className="cap glass deep"
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
      >
        <textarea
          id="prompt"
          ref={ref}
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          aria-label="Message"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <div className="tools">
          <span className="pil" title={integrations?.model ? `Model: ${integrations.model_id}` : "No model connected"}>
            <IconModel />
            {integrations?.model ? "Claude" : "No model"}
          </span>
          <span className="pil on" title="Always on: Warden never pays or cancels anything without a family approver's yes.">
            <IconCheck />
            <span>
              Family approves<span className="lg"> payments</span>
            </span>
          </span>
          <button className="go" type="submit" aria-label="Send" disabled={disabled || busy || !value.trim()}>
            <IconSend />
          </button>
        </div>
      </form>
      <div className={`demoNote ${note.tone === "warn" ? "warn" : ""}`}>
        {note.tone === "warn" ? <IconWarn /> : <IconInfo />}
        {note.text}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const household = useActiveHousehold();
  const status = useApp((s) => s.status);
  const me = useApp((s) => s.me);
  const integrations = useApp((s) => s.integrations);
  const conversations = useApp((s) => s.conversations);
  const activeConversation = useApp((s) => s.activeConversation);
  const customAgents = useApp((s) => s.customAgents);
  const chatAgent = useApp((s) => s.chatAgent);
  const autoRun = useApp((s) => s.autoRun);
  const { setConversation, setCrumb, refreshCounts, refreshConversations } = useApp.getState();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState<Live | null>(null);
  const [input, setInput] = useState("");
  const created = useRef<string | null>(null);

  const ready = status === "ready" && Boolean(household);
  const modelReady = Boolean(integrations?.model);
  const conversation = conversations.find((c) => c.id === activeConversation) ?? null;
  // A chat with an agent the family made (null = Milo).
  const agentRef = activeConversation ? customRefOf(conversation?.active_participants) : chatAgent;
  const custom = agentRef ? customAgents.find((a) => a.ref === agentRef) ?? null : null;
  const agentGone = Boolean(agentRef && !custom);
  const canSend = ready && modelReady && !agentGone;
  const speaker = speakerFor(agentRef ?? "milo", customAgents);
  const elderName = household?.members.find((m) => m.role === "elder")?.display_name ?? "the account owner";
  const myRole = household?.my_role;

  useEffect(() => {
    setCrumb(conversation?.title || (activeConversation ? "Chat" : custom ? custom.name : "New task"));
  }, [conversation?.title, activeConversation, custom, setCrumb]);

  const load = useCallback(async (id: string, householdId: string | null) => {
    const [msgs, apprs] = await Promise.all([
      api<ChatMessage[]>(`/conversations/${id}/messages`),
      householdId ? api<Approval[]>(`/approvals?household_id=${householdId}`).catch(() => [] as Approval[]) : Promise.resolve([] as Approval[]),
    ]);
    setMessages(msgs);
    setApprovals(apprs.filter((a) => a.conversation_id === id));
  }, []);

  useEffect(() => {
    if (!activeConversation || !household) {
      setLive(null);
      setMessages([]);
      setApprovals([]);
      return;
    }
    // A chat we just created already shows the optimistic first message
    // and the reply streaming in; reloading here would wipe both.
    if (created.current === activeConversation) return;
    setLive(null);
    let cancelled = false;
    setLoading(true);
    setMessages([]);
    setApprovals([]);
    load(activeConversation, household.id)
      .catch(() => {
        if (!cancelled) setConversation(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [activeConversation, household, load, setConversation]);

  // Follow the conversation while it grows, unless the reader scrolled up.
  useEffect(() => {
    const pane = document.getElementById("pane");
    if (!pane) return;
    const near = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 160;
    if (near || live?.text === "") requestAnimationFrame(() => (pane.scrollTop = pane.scrollHeight));
  }, [messages, live, approvals]);

  async function send(override?: string) {
    const text = (override ?? input).trim();
    if (!text || !canSend || !household || (live && !live.error)) return;
    if (override === undefined) setInput("");
    let id = activeConversation;
    const who = agentRef ?? "milo";
    try {
      if (!id) {
        const today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" });
        const title = custom ? `${custom.name} · ${text === RUN_NOW_TEXT ? today : text.slice(0, 40)}` : text.slice(0, 60);
        const conv = await api<Conversation>("/conversations", {
          body: { household_id: household.id, title, active_participants: agentRef ? [agentRef] : undefined },
        });
        id = conv.id;
        created.current = id;
        // Listed right away, so the chat keeps its agent while the list reloads.
        useApp.setState((s) => ({ conversations: [conv, ...s.conversations] }));
        setConversation(id);
        void refreshConversations();
      }
    } catch (e) {
      setLive({ agent: who, text: "", tool: null, error: e instanceof Error ? e.message : "Couldn't start a chat." });
      return;
    }
    setMessages((m) => [
      ...m,
      { id: `local-${Date.now()}`, role: "user", agent_id: null, content: text, created_at: new Date().toISOString() },
    ]);
    setLive({ agent: who, text: "", tool: null, error: null });
    const pane = document.getElementById("pane");
    requestAnimationFrame(() => pane && (pane.scrollTop = pane.scrollHeight));
    try {
      await streamChat(id, text, (e) => {
        if (e.event === "start") setLive((l) => l && { ...l, agent: e.data.agent_id });
        else if (e.event === "delta") setLive((l) => l && { ...l, text: l.text + e.data.content, tool: null });
        else if (e.event === "tool") setLive((l) => l && { ...l, tool: e.data.status, agent: e.data.agent || l.agent });
        else if (e.event === "reset") setLive((l) => l && { ...l, text: "" });
        else if (e.event === "error") setLive((l) => l && { ...l, error: e.data.message, tool: null });
      });
    } catch (err) {
      setLive((l) => l && { ...l, error: err instanceof Error ? err.message : "Couldn't reach Warden." });
    }
    await load(id, household.id).catch(() => undefined);
    created.current = null;
    void refreshCounts();
    void refreshConversations();
    setLive((l) => (l?.error ? { agent: l.agent, text: "", tool: null, error: l.error } : null));
  }

  // "Run now" from an agent's sheet: start its job as soon as chat can send.
  useEffect(() => {
    if (!autoRun || !canSend || activeConversation) return;
    useApp.setState({ autoRun: 0 });
    void send(RUN_NOW_TEXT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, canSend, activeConversation]);

  function resolved(a: Approval) {
    setApprovals((list) => list.map((x) => (x.id === a.id ? a : x)));
    if (activeConversation && household) void load(activeConversation, household.id);
    void refreshCounts();
  }

  const note: { tone: "info" | "warn"; text: string } =
    status === "loading"
      ? { tone: "info", text: "Connecting to Warden…" }
      : status === "offline"
        ? { tone: "warn", text: "Chat is off: Warden's API isn't connected to this site yet. Nothing here is scripted." }
        : status !== "ready"
          ? { tone: "warn", text: "Chat is off: can't reach Warden's API right now." }
          : !modelReady
            ? { tone: "warn", text: `The model isn't connected on this server yet, so ${speaker.name} can't reply. Nothing here is scripted.` }
            : agentGone
              ? { tone: "warn", text: "This agent was deleted, so it can't answer anymore. The chat stays here for your records." }
              : custom
                ? { tone: "info", text: `${custom.name} is read-only: it reads the accounts and reports back, and can't pay, cancel or ask for approvals. AI can make mistakes.` }
                : integrations?.stripe_mode === "live"
              ? { tone: "info", text: "Live AI replies. AI can make mistakes — check before you approve." }
              : { tone: "info", text: "Live AI replies — AI can make mistakes. Payments run in test mode: no real money moves." };

  const placeholder = !canSend
    ? agentGone
      ? "This agent was deleted"
      : "Chat is off for now"
    : messages.length || custom
      ? `Message ${speaker.name}…`
      : myRole === "approver"
        ? `Ask about ${elderName}'s accounts — Milo checks with the family before anything moves.`
        : "Ask for anything — Milo checks with your family before any money moves.";

  const pending = approvals.filter((a) => a.status === "pending");
  const inThread = messages.length > 0 || live !== null || loading;
  const composer = (
    <Composer value={input} onChange={setInput} onSend={() => void send()} disabled={!canSend} busy={Boolean(live && !live.error)} placeholder={placeholder} note={note} />
  );

  if (!inThread && custom) {
    return (
      <div className="hello">
        <Toy kind={custom.kind} own className="mark toy" />
        <h1>Chat with {custom.name}</h1>
        <p className="sub">
          {scheduleShort(custom.schedule)} · read-only. Ask it to run its job, or ask it anything about the accounts.
        </p>
        {composer}
        <div className="sugs">
          <button className="sug" disabled={!canSend} onClick={() => void send(RUN_NOW_TEXT)}>
            Run your job now
          </button>
          <button className="sug" onClick={() => setConversation(null)}>
            Back to Milo
          </button>
        </div>
      </div>
    );
  }

  if (!inThread) {
    return (
      <div className="hello">
        <Toy kind="beacon" className="mark toy" />
        <h1>What should Warden handle today?</h1>
        {composer}
        <div className="sugs">
          {suggestions(myRole, elderName).map((s) => (
            <button
              key={s}
              className="sug"
              disabled={!canSend}
              onClick={() => {
                setInput(s);
                document.getElementById("prompt")?.focus();
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const liveAgent = speakerFor(live?.agent, customAgents);
  return (
    <div className="threadwrap">
      <div className="thread" aria-live="polite">
        {loading && <Spinner label="Loading the conversation" />}
        {household && myRole === "approver" && !household.my_scopes.includes("view_accounts") && (
          <Notice>{elderName} hasn&apos;t shared their accounts with you, so {speaker.name} can only talk in general terms.</Notice>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="msg user">
              <span className="av" aria-hidden="true">
                {(me?.display_name || "?")[0]}
              </span>
              <div className="col">
                <div className="bubble">{m.content}</div>
              </div>
            </div>
          ) : m.role === "system" ? (
            <div key={m.id} className="msg agent event">
              <Toy kind="lock" />
              <div className="col">
                <span className="who">Warden</span>
                <div className="bubble">{m.content}</div>
              </div>
            </div>
          ) : (
            <div key={m.id} className="msg agent">
              <Toy kind={speakerFor(m.agent_id, customAgents).kind} own={speakerFor(m.agent_id, customAgents).own} />
              <div className="col">
                <span className="who">{speakerFor(m.agent_id, customAgents).name}</span>
                <div className="bubble md">
                  <Markdown text={m.content} />
                </div>
              </div>
            </div>
          ),
        )}

        {pending.map((a) => (
          <ApprovalCard key={a.id} approval={a} variant="bubble" onResolved={resolved} />
        ))}

        {live && live.text && (
          <div className="msg agent">
            <Toy kind={liveAgent.kind} own={liveAgent.own} />
            <div className="col">
              <span className="who">{liveAgent.name}</span>
              <div className="bubble md">
                <Markdown text={live.text} />
              </div>
            </div>
          </div>
        )}
        {live && !live.error && (live.tool || !live.text) && (
          <div className="plan" role="status">
            <Toy kind={liveAgent.kind} own={liveAgent.own} />
            <span>{live.tool ? `${live.tool}` : `${liveAgent.name} is working on it`}</span>
            <span className="dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
        {live?.error && <Notice tone="err">{live.error}</Notice>}
      </div>
      <div className="dock">{composer}</div>
    </div>
  );
}
