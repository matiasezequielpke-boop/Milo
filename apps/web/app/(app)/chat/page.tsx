"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Markdown } from "@/components/Markdown";
import { Notice, ShieldIcon, Spinner } from "@/components/ui";
import { api, streamChat } from "@/lib/api";
import { useActiveHousehold, useApp } from "@/lib/store";
import type { Approval, ChatMessage, Conversation } from "@/lib/types";

const SUGGESTIONS_ELDER = [
  "Is there anything strange on my account?",
  "What subscriptions am I paying for?",
  "Please pay my electric bill",
];
const SUGGESTIONS_APPROVER = [
  "Any suspicious charges this week?",
  "What's waiting for my approval?",
  "Which subscriptions started recently?",
];

type Live = { text: string; tool: string | null; error: string | null };

export default function ChatPage() {
  const household = useActiveHousehold();
  const integrations = useApp((s) => s.integrations);
  const refreshCounts = useApp((s) => s.refreshCounts);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<Live | null>(null);
  const [loading, setLoading] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);

  const canApprove = Boolean(household?.my_scopes.includes("approve_actions"));
  const modelReady = integrations?.model !== false;
  const canView = Boolean(household?.my_scopes.includes("view_accounts"));

  const loadMessages = useCallback(async (conv: Conversation) => {
    const [msgs, apprs] = await Promise.all([
      api<ChatMessage[]>(`/conversations/${conv.id}/messages`),
      api<Approval[]>(`/approvals?household_id=${conv.household_id}`).catch(() => [] as Approval[]),
    ]);
    setMessages(msgs);
    setApprovals(apprs.filter((a) => a.conversation_id === conv.id));
  }, []);

  useEffect(() => {
    if (!household) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      const list = await api<Conversation[]>(`/conversations?household_id=${household.id}`);
      const conv =
        list[0] ?? (await api<Conversation>("/conversations", { body: { household_id: household.id, title: "Chat" } }));
      if (cancelled) return;
      setConversation(conv);
      await loadMessages(conv);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [household, loadMessages]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, live, approvals]);

  async function newChat() {
    if (!household) return;
    const conv = await api<Conversation>("/conversations", { body: { household_id: household.id, title: "Chat" } });
    setConversation(conv);
    setMessages([]);
    setApprovals([]);
  }

  async function send(text: string) {
    if (!conversation || !text.trim() || live || !modelReady) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { id: `local-${Date.now()}`, role: "user", agent_id: null, content: text, created_at: new Date().toISOString() },
    ]);
    setLive({ text: "", tool: null, error: null });
    try {
      await streamChat(conversation.id, text, (e) => {
        if (e.event === "delta") setLive((l) => l && { ...l, text: l.text + e.data.content, tool: null });
        else if (e.event === "tool") setLive((l) => l && { ...l, tool: e.data.status });
        else if (e.event === "reset") setLive((l) => l && { ...l, text: "" });
        else if (e.event === "error") setLive((l) => l && { ...l, error: e.data.message, tool: null });
      });
    } catch (err) {
      setLive((l) => l && { ...l, error: err instanceof Error ? err.message : "Couldn't reach Warden." });
    }
    await loadMessages(conversation);
    void refreshCounts();
    setLive((l) => (l?.error ? { text: "", tool: null, error: l.error } : null));
  }

  function resolved(a: Approval) {
    setApprovals((list) => list.map((x) => (x.id === a.id ? a : x)));
    if (conversation) void loadMessages(conversation);
    void refreshCounts();
  }

  if (!household) return null;
  const suggestions = household.my_role === "elder" ? SUGGESTIONS_ELDER : SUGGESTIONS_APPROVER;
  const pending = approvals.filter((a) => a.status === "pending");

  return (
    <div className="flex h-[calc(100vh-7.5rem)] flex-col md:h-screen">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 sm:px-8">
        <p className="text-white/60">
          Talking with <span className="text-white">Milo</span>
          <span className="hidden text-white/40 sm:inline"> · money actions go through Warden and your family</span>
        </p>
        <button onClick={newChat} className="text-sm text-white/60 hover:text-white">
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-chat space-y-6 px-4 py-8 sm:px-6">
          {integrations && !integrations.model && (
            <Notice tone="amber">
              The model isn&apos;t connected on this server yet (ANTHROPIC_API_KEY), so Milo can&apos;t answer. Nothing in
              this chat is ever scripted.
            </Notice>
          )}
          {!canView && (
            <Notice>
              You can chat, but {household.members.find((m) => m.role === "elder")?.display_name ?? "the account owner"}{" "}
              hasn&apos;t shared their accounts with you yet.
            </Notice>
          )}
          {loading && <Spinner />}
          {!loading && modelReady && messages.length === 0 && !live && (
            <div className="pt-10 text-center">
              <p className="text-3xl font-semibold tracking-tight text-white">How can I help?</p>
              <div className="mt-8 flex flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-white/15 px-4 py-2 text-[0.95rem] text-white/75 hover:border-white/40 hover:text-white"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-white/10 px-5 py-3 text-white">{m.content}</div>
              </div>
            ) : m.role === "system" ? (
              <div key={m.id} className="flex items-start gap-3 rounded-2xl border border-white/15 px-4 py-3 text-[0.95rem] text-white/80">
                <ShieldIcon className="mt-1 h-4 w-4 shrink-0" />
                <span>{m.content}</span>
              </div>
            ) : (
              <div key={m.id} className="text-white/90">
                <Markdown text={m.content} />
              </div>
            ),
          )}

          {pending.map((a) => (
            <ApprovalCard key={a.id} approval={a} canApprove={canApprove} onResolved={resolved} />
          ))}

          {live && (
            <div className="space-y-3 text-white/90">
              {live.text && <Markdown text={live.text} />}
              {live.tool && (
                <p className="flex items-center gap-2 text-sm text-white/50">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-white/60" /> {live.tool}…
                </p>
              )}
              {!live.text && !live.tool && !live.error && <Spinner label="Thinking" />}
              {live.error && <Notice tone="red">{live.error}</Notice>}
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="border-t border-white/10 px-4 py-4 sm:px-6"
      >
        <div className="mx-auto flex max-w-chat items-end gap-2 rounded-3xl border border-white/15 bg-ink-900 p-2 focus-within:border-white/40">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={1}
            placeholder={modelReady ? "Ask about a charge or a bill…" : "Chat is off until the model is connected"}
            disabled={!modelReady}
            aria-label="Message"
            className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-white placeholder:text-white/35 outline-none"
          />
          <button
            type="submit"
            disabled={!modelReady || !input.trim() || Boolean(live && !live.error)}
            className="h-11 shrink-0 rounded-full bg-white px-5 font-medium text-black disabled:opacity-30"
          >
            Send
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-chat text-center text-xs text-white/35">
          Milo never moves money on its own. Payments and cancellations need your family approver&apos;s OK.
        </p>
      </form>
    </div>
  );
}
