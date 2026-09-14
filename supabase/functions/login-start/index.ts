// Milo -- login-start
// Step 1 of the two-step login: verify email+password, then trigger Supabase's
// built-in one-time email code. Step 2 is a plain client-side
// supabase.auth.verifyOtp() call -- no second function needed for that part.
//
// This function deliberately never returns a session. The password check
// below issues one internally, but it is immediately signed out again so the
// only way the browser gets a real session is by confirming the emailed code.

import { createClient } from "jsr:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return json({ error: "method_not_allowed" }, 405);
  }

  let email = "";
  let password = "";
  try {
    const body = await req.json();
    email = String(body.email ?? "").trim().toLowerCase();
    password = String(body.password ?? "");
  } catch {
    return json({ error: "invalid_body" }, 400);
  }

  if (!email || !password) {
    return json({ error: "missing_fields" }, 400);
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  // Step 1: verify the password is actually correct for this email.
  const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (signInError || !signInData.session) {
    // Same message whether the account doesn't exist or the password is wrong --
    // don't leak which one it was.
    return json({ error: "invalid_credentials" }, 401);
  }

  // The check above already issued a valid session. The client must not receive
  // it -- drop it now so the only way in is through the emailed code.
  await supabase.auth.signOut();

  // Step 2: ask Supabase to email a one-time code to this address.
  // shouldCreateUser: false -- this is a login path, not a signup path.
  const { error: otpError } = await supabase.auth.signInWithOtp({
    email,
    options: { shouldCreateUser: false },
  });

  if (otpError) {
    return json({ error: "otp_send_failed", message: otpError.message }, 500);
  }

  return json({ ok: true });
});
