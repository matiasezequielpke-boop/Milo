// Two ways in:
// - A real account: a Supabase session that this app's API opened (sign-up,
//   or password + emailed code). Kept in localStorage and refreshed before
//   it expires (lib/api.ts).
// - The demo family, when the API runs in DEMO_MODE: `demo:<email>`.
export type Session = { access_token: string; refresh_token: string; expires_at: number; email: string };

const SESSION_KEY = "warden.session";
const DEMO_KEY = "warden.demoEmail";

let session: Session | null | undefined;
let demo: string | null | undefined;

function read<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the sign-in just won't survive a reload */
  }
}

export function getSession(): Session | null {
  if (session === undefined) session = typeof window === "undefined" ? null : read<Session>(SESSION_KEY);
  return session;
}

export function setSession(next: Session | null) {
  session = next;
  write(SESSION_KEY, next);
  if (next) setDemoEmail(null);
}

export function getDemoEmail(): string | null {
  if (demo === undefined) demo = typeof window === "undefined" ? null : read<string>(DEMO_KEY);
  return demo;
}

export function setDemoEmail(email: string | null) {
  demo = email;
  write(DEMO_KEY, email);
}

export function currentToken(): string | null {
  const s = getSession();
  if (s) return s.access_token;
  const d = getDemoEmail();
  return d ? `demo:${d}` : null;
}
