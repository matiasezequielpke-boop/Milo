# Sign-in setup (Supabase)

How accounts work:

- **Sign up:** email + password, tick "18 or older" and "I agree to the Terms…" → the person is in straight away.
- **Log in:** email + password → Supabase emails a 6-digit code → the person types it → they're in.

The API (`apps/api/app/routers/auth.py`) runs both flows in front of Supabase Auth. A Supabase session only works with the API if the API opened it (`auth_sessions` table). That means skipping a step gets you nowhere: a session taken straight from Supabase with just the password, or with just an emailed code, is refused. Tests: `apps/api/tests/test_auth.py`.

## What to configure

### 1. API environment (the server that runs `apps/api`)

In production this is the Vercel project `warden-api` with the Supabase project `warden` (ref `qtlnrxfbdtckruwtekhb`). The URL, publishable key, site/API URLs and CORS are already set there (as `WARDEN_SUPABASE_*` and the rest — see [deploy.md](deploy.md)); the service role key and the database URL are the owner's to add.

| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API → `anon` / publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Same page, `service_role` / secret key. **Server only**: never in the web app or a `NEXT_PUBLIC_` variable. Lets sign-up create an already-confirmed account (so the person is in straight away) and lets account deletion remove the Supabase user. |
| `WEB_APP_URL` | The site's public URL (invite and unsubscribe links) |
| `PUBLIC_API_URL` | The API's public URL (enables one-click unsubscribe in email headers) |
| `CORS_ORIGINS` | The site's public URL |

Leave `DEMO_MODE` off for real accounts. If it's on, the login page also offers "Explore the demo family". Demo mode refuses to start with live payments, live Stripe keys or Plaid production.

### 2. Supabase dashboard (one time)

**The login code email.** With `RESEND_API_KEY` set on the API (the production setup), Warden emails the code itself: Supabase only generates it (admin `generate_link`, which sends nothing), so Supabase's email templates and SMTP aren't involved, and items 1 and 4 below don't apply. Resend's test sender (`EMAIL_FROM=Warden <onboarding@resend.dev>`) only delivers to the Resend account's own address; verify a domain at Resend before inviting anyone else. Without `RESEND_API_KEY`, Supabase sends the code as described below. Note that Supabase only lets you edit its templates once custom SMTP is set up.

1. **Authentication → Emails → "Magic Link" template:** include the code, e.g.
   ```html
   <h2>Your Warden sign-in code</h2>
   <p>Enter this code to finish logging in: <strong>{{ .Token }}</strong></p>
   <p>It expires in 10 minutes. If you didn't try to log in, ignore this email — your password alone can't get anyone in.</p>
   ```
   Without `{{ .Token }}` the email only has a link. That link creates a session the API refuses, so the code must be in the email.
2. **Authentication → Providers → Email:** enabled (default). "Confirm email" can stay on, because sign-up with the service role key creates confirmed accounts.
3. **Authentication → Settings:** email OTP expiry 600 seconds (10 minutes, matching the app's window). OTP length 6.
4. **Authentication → Emails → SMTP Settings:** set up custom SMTP (e.g. Resend). Supabase's built-in sender is only meant for testing: it sends very few emails per hour and may only deliver to your own team's addresses, so real users wouldn't get their codes.
5. **Edge Functions:** delete the old `login-start` function. The API replaces it. It's harmless now, since sessions it leads to are refused, but it shouldn't be left around.

### 3. Web app environment (Vercel project `milo`)

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | The API's public URL (set: `https://warden-api-three.vercel.app`) |
| `NEXT_PUBLIC_BUSINESS_NAME` | Legal company name, once incorporated (default "Warden") |
| `NEXT_PUBLIC_BUSINESS_ADDRESS` | Registered address, once it exists |
| `NEXT_PUBLIC_CONTACT_EMAIL` | Support / privacy contact |

Until the last two are set, the legal pages say the details will be published before launch. No made-up details are shown.

## Limits built in

- 5 wrong passwords per email per 15 minutes → "Too many attempts".
- A password check opens a 10-minute window for the code. Up to 3 code emails per window, and 5 wrong codes close it.
- Sign-in attempt records are deleted after 30 days.
- Supabase's own rate limits also apply (for example, one code email per address per 60 seconds).
