// No sign-in for now: the API runs in DEMO_MODE and accepts
// `Bearer demo:<email>` for the two demo people only (Rosa, the account
// owner, and Ana, her approver). Which one you're viewing as is a
// per-browser convenience, so it lives in localStorage.
const KEY = "warden.demoEmail";
let current: string | null = null;

export function getDemoEmail(): string | null {
  if (current) return current;
  try {
    current = window.localStorage.getItem(KEY);
  } catch {
    current = null;
  }
  return current;
}

export function setDemoEmail(email: string) {
  current = email;
  try {
    window.localStorage.setItem(KEY, email);
  } catch {
    /* storage unavailable: the choice just won't survive a reload */
  }
}

export function getToken(): string | null {
  const email = getDemoEmail();
  return email ? `demo:${email}` : null;
}
