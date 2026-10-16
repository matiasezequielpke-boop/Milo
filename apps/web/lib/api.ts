import { getToken } from "@/lib/auth";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function headers(extra?: HeadersInit): Promise<HeadersInit> {
  const token = await getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(extra || {}),
  };
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e as { msg?: string }).msg || "").filter(Boolean).join("; ");
  }
  return fallback;
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: init?.method || (init?.body !== undefined ? "POST" : "GET"),
    headers: await headers(),
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, `Request failed (${res.status})`));
  return body as T;
}

export type StreamEvent =
  | { event: "start"; data: { agent_id: string; model: string } }
  | { event: "delta"; data: { content: string } }
  | { event: "tool"; data: { name: string; status: string; agent: string } }
  | { event: "approval"; data: { approval: { id: string; summary: string; action_type: string; status: string } } }
  | { event: "reset"; data: Record<string, never> }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { message_id: string | null } };

/** POST + Server-Sent Events. EventSource can't POST, so this reads the
 *  response body stream and splits it on blank lines. */
export async function streamChat(
  conversationId: string,
  content: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: await headers({ Accept: "text/event-stream" }),
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detail(body, `Request failed (${res.status})`));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent({ event, data: JSON.parse(data) } as StreamEvent);
    }
  }
}
