import { currentToken, getSession, setSession } from "@/lib/auth";

// No API configured → null, and the app says so instead of calling
// localhost from a public page. In `next dev` it defaults to the local API.
const configured = process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");
export const API_URL: string | null = configured ? configured.replace(/\/$/, "") : null;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

/** Swaps the refresh token for a new access token (same session). Any
 *  failure ends the session — the person logs in again. */
async function refreshSession(): Promise<boolean> {
  const s = getSession();
  if (!s || !API_URL) return false;
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: s.refresh_token }),
      });
      if (!res.ok) throw new Error("refresh failed");
      const body = await res.json();
      setSession({ access_token: body.access_token, refresh_token: body.refresh_token, expires_at: body.expires_at, email: s.email });
      return true;
    } catch {
      endSession();
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

function endSession() {
  if (!getSession()) return;
  setSession(null);
  window.dispatchEvent(new Event("warden:signed-out"));
}

async function headers(extra?: HeadersInit): Promise<HeadersInit> {
  const s = getSession();
  if (s && s.expires_at * 1000 - Date.now() < 60_000) await refreshSession();
  const token = currentToken();
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

async function send(path: string, init: RequestInit): Promise<Response> {
  if (!API_URL) throw new ApiError(0, "Warden's API isn't connected to this site yet.");
  try {
    return await fetch(`${API_URL}${path}`, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "Can't reach Warden's API right now.");
  }
}

async function request(path: string, init: { method?: string; body?: unknown; accept?: string }, retry = true): Promise<Response> {
  const res = await send(path, {
    method: init.method || (init.body !== undefined ? "POST" : "GET"),
    headers: await headers(init.accept ? { Accept: init.accept } : undefined),
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 401 && retry && getSession()) {
    if (await refreshSession()) return request(path, init, false);
  } else if (res.status === 401 && getSession()) {
    endSession();
  }
  return res;
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await request(path, init || {});
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, `Request failed (${res.status})`));
  return body as T;
}

/** For downloads (the data export): the raw response as a Blob. */
export async function apiBlob(path: string): Promise<Blob> {
  const res = await request(path, {});
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detail(body, `Request failed (${res.status})`));
  }
  return res.blob();
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
  const res = await send(`/conversations/${conversationId}/messages`, {
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
