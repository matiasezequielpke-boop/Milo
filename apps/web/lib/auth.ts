// Two ways to be signed in:
// - Supabase email OTP (production): the access token from the session.
// - Dev login (local only): `dev:<email>`, accepted by the API only when it
//   runs with DEV_AUTH_ENABLED in APP_ENV=development.
import { supabase } from "@/lib/supabaseClient";

const DEV_KEY = "warden.devEmail";

export function getDevEmail(): string | null {
  try {
    return window.localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

export function setDevEmail(email: string | null) {
  try {
    if (email) window.localStorage.setItem(DEV_KEY, email.trim().toLowerCase());
    else window.localStorage.removeItem(DEV_KEY);
  } catch {
    /* storage unavailable: dev login just won't persist */
  }
}

export async function getToken(): Promise<string | null> {
  const dev = getDevEmail();
  if (dev) return `dev:${dev}`;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function signOut() {
  setDevEmail(null);
  await supabase.auth.signOut();
}
