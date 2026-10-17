# Compliance checklist (17 Oct 2026)

The 20 "so your app doesn't get sued" items, mapped to what the code now does. This is engineering work, **not legal advice**. Everything below still needs a fintech lawyer's review before public launch (open questions are at the end).

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Privacy policy | Done. Written to match what the code actually collects and shares | `/privacy` (`apps/web/app/(legal)/privacy`) |
| 2 | Terms of service | Done. Governing law is left for incorporation | `/terms` |
| 3 | Refund policy | Done. Free during the pilot; payment refunds come from the payee; paid plans need 30 days' notice | `/refunds` |
| 4 | Cookie policy | Done. Lists every item kept in the browser | `/cookies` |
| 5 | Cookie consent banner | Done as a **notice**: Warden sets no cookies and runs no analytics, so nothing needs consent. Optional storage must ask first, with "No" as easy as "Yes" | `components/CookieNotice.tsx` |
| 6 | Check form consents | Done. Sign-up needs two unticked-by-default boxes (18+, Terms + Privacy); the API rejects sign-up without them and stores the version and time. Family sharing stays explicit, per scope, revocable and versioned | `routers/auth.py` (signup), `users.terms_*`, `age_confirmed_at` |
| 7 | No unnecessary data | Done. Sign-up asks only email + password; no phone, address, birth date or ID; no IP addresses stored; sign-in attempt records deleted after 30 days; internals (hashes, cursors, tokens) excluded from exports; push notifications carry no content | `routers/auth.py`, `notify.py`, `routers/account.py` |
| 8 | Audit third-party SDKs | Done. Inventory below. The web app loads no third-party scripts except Plaid Link, and only when someone connects a bank. Fonts are self-hosted | below |
| 9 | Remove dark patterns | Reviewed. Boxes unticked by default; one-click unsubscribe; deletion in Settings (typed confirmation only); the cookie notice isn't a consent wall; Approve and Block shown side by side; no countdowns, fake scarcity or confirmshaming | — |
| 10 | Remove hidden fees | Done. No fees exist; the approval card says "Warden fee: None — the payee gets the amount shown"; Terms and Refunds say future fees need 30 days' notice and opt-in | `ApprovalCard.tsx`, `/terms`, `/refunds` |
| 11 | Remove fake reviews | Checked: there are no reviews, testimonials, ratings or user counts. The prototype's invented agent stats were removed earlier | — |
| 12 | Remove unsupported claims | Done. Copy only claims what the code enforces. The chat note says AI can make mistakes and only says "no real money moves" when Stripe isn't live; agents that don't exist are labelled "Coming soon" | `app/(app)/page.tsx`, `lib/agents.ts` |
| 13 | Accessibility alt text | Done. Decorative mascots are hidden from screen readers (the name is always written next to them); standalone ones have a label; icon-only buttons have `aria-label`s | `components/Toy.tsx` |
| 14 | Fix color contrast | Done. Text and button colors rechecked to WCAG AA (4.5:1) in light and dark | `app/globals.css` tokens |
| 15 | Keyboard navigation | Done. "Skip to content" link; visible focus rings (including the chat box); the agent sheet keeps Tab inside and closes with Esc; closed menus and the mobile drawer are out of the tab order | `Shell.tsx`, `AgentSheet.tsx`, `globals.css` |
| 16 | Add business details | Done, config-driven. `NEXT_PUBLIC_BUSINESS_NAME/ADDRESS`, `NEXT_PUBLIC_CONTACT_EMAIL` (web) and `BUSINESS_*`, `CONTACT_EMAIL` (email footers). Until the company exists, the pages say so instead of inventing an address | `lib/legal.ts`, `components/Legal.tsx`, `notify.py` |
| 17 | Age consent for kids' data | Done. 18+ only, confirmed at sign-up and enforced by the API; the privacy policy explains deletion if a minor's data is found | `routers/auth.py`, `/privacy` |
| 18 | Unsubscribe link in emails | Done. Every notification email has a footer link plus `List-Unsubscribe` and one-click (RFC 8058) headers. Opted-out people are skipped; Settings has an on/off switch; sign-in codes always arrive | `notify.py`, `POST /email/unsubscribe`, `/unsubscribe`, Settings |
| 19 | License fonts/images | Done. Fonts are OFL 1.1, self-hosted; mascots are original; icons credited (Feather, MIT); all dependencies are permissive | `THIRD_PARTY_NOTICES.md`, `/licenses` |
| 20 | Data deletion request | Done. Settings → Delete your account: removes the household (Plaid access revoked via `/item/remove`) or the approver's access, plus chats, sessions and the Supabase user. Settings → Download your data gives a JSON export | `routers/account.py`, Settings, `tests/test_account.py` |

## Data inventory

| Data | Why | Where | Kept |
|---|---|---|---|
| Email, password (hashed) | Sign-in | Supabase Auth | Until account deletion |
| Terms version, consent times | Proof of consent | `users` | Until account deletion |
| Names / emails of invited family | Family set-up | `household_members` | Until removed or deleted |
| Consent scopes and history | Who may see what | `consents` | With the household |
| Bank accounts, balances, 2 years of transactions | Detection, answers | `bank_*` (Plaid token encrypted in `credentials`) | With the household |
| Alerts, bills, approvals, payments | The service | Warden tables | With the household |
| Chat messages | Chat | `conversations`, `messages` | Until account deletion |
| Agents people make (name, face, job text, schedule, maker, last run) | Custom agents | `custom_agents`; their reports are chats | With the household; an approver's agents go when they delete their account |
| Activity log | Family record | `audit_log` | With the household |
| Sign-in attempts (email, time) | Rate limiting | `login_challenges` | 30 days |
| Sessions | Login gate | `auth_sessions` | Until account deletion |

## Third-party SDKs and services

| Service | Used for | Active when | Data sent |
|---|---|---|---|
| Supabase | Auth, database | Always | Credentials, all stored data |
| Plaid (`plaid-python`, Link script) | Read-only bank data | `PLAID_*` set | Bank login happens in Plaid's window |
| Anthropic (`anthropic`) | Chat model | `ANTHROPIC_API_KEY` set | Messages + data needed to answer |
| Stripe (`stripe`) | Approved payments | `STRIPE_SECRET_KEY` set | Payee, amount, reference |
| Resend (HTTP API) | Notification emails | `RESEND_API_KEY` set | Recipient email, message |
| ntfy.sh (HTTP) | Push | `NTFY_TOPIC` set | A content-free "something needs attention" |
| Vercel | Web hosting | Always | Web requests |
| LiteLLM, Tavily, E2B | Older Milo scaffolding (Scout/Ledger tools, non-household chat) | Only with their keys; **none set** | — consider removing before launch |

## Open questions for the lawyer

1. GLBA: does Warden count as a "financial institution" that needs a GLBA privacy notice and safeguards program?
2. Money movement: is Stripe-executed bill pay on the elder's behalf money transmission in any state? (See `money-plan.md`.)
3. E-SIGN consent for electronic disclosures, if needed.
4. Governing law and venue, arbitration or not, limitation of liability wording.
5. Elder-specific rules (e.g. state elder financial exploitation statutes, mandatory reporting) and how approver consent should be documented.
6. Plaid production needs a public privacy policy URL: `/privacy` is ready once business details are filled in.
