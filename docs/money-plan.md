# How money moves in Warden (MVP) — and what changes before real money

This is the engineering view: what the code does today, the guarantees it
enforces, and the open questions for a fintech lawyer. It is not legal
advice and draws no legal conclusions.

## Principle

Warden never holds anyone's money. It reads accounts through a licensed
data aggregator (Plaid) and, after a human approves, instructs a licensed
payment processor (Stripe) to move funds directly from the account owner
to the payee.

## The one path to moving money

```
Milo (chat) or an "Ask to pay" button
        │  proposes — never executes
        ▼
app/warden.py  propose_bill_payment()  ──►  approval_requests (pending)
        │                                    + email/push to approvers
        │                                    + notice to the account owner
        ▼
A family approver with the elder's `approve_actions` consent taps Approve
        │  (the elder can always Block; the elder cannot approve their own)
        ▼
app/executor.py  execute()  ──►  Stripe PaymentIntent (idempotent on the approval id)
        │
        ▼
audit_log (append-only) + event posted back into the conversation
```

Enforced in code and covered by tests (`apps/api/tests/test_family_flow.py`):

- The model has no tool that executes anything. Its money tools create approval requests and return.
- Approval requires the `approve_actions` scope, which only the elder can grant and can revoke at any time.
- What runs is exactly what was approved: the executor re-checks the bill amount and payee before calling Stripe; if the bill changed, nothing is sent.
- A payee is blocked once the family marks one of its charges as fraud; Warden then refuses to propose paying it.
- Requests expire after 72 hours; expired equals denied.
- Stripe's idempotency key is the approval id, so retries can't pay twice.
- Live Stripe keys are refused unless `PAYMENTS_LIVE_ENABLED=true` is set deliberately.

## Today (test mode)

| Step | Provider | Mode |
|---|---|---|
| Read balances and transactions | Plaid `transactions/sync` | Sandbox (test institutions) |
| Pay a bill | Stripe PaymentIntent, confirmed server-side | Test mode, test card `pm_card_visa` |
| Cancel a subscription | None — Warden prepares the cancellation request; a person sends it | n/a |
| "Block" a fraudulent charge | Warden marks it and blocks the payee in Warden; the bank must stop the card | n/a |

## Before any real money

1. **Paying instrument.** Replace the test card with the elder's own bank account: Plaid Auth → Stripe processor token → ACH Direct Debit `PaymentMethod` (mandate collected from the account owner). Settlement becomes asynchronous (`processing` → `succeeded`); handle it via Stripe webhooks (not built yet).
2. **Funds flow.** Payees receive funds directly (Stripe Connect destination charges via `payees.stripe_account_id`), or bills are paid through a bill-pay partner. Either way Warden's own balance never holds customer money.
3. **Card blocking.** Real "block" means issuer-side controls (the bank's own card lock, or a card issued through a program partner). Out of MVP scope.
4. **Webhooks.** Plaid `SYNC_UPDATES_AVAILABLE` (with signature verification) for near-real-time alerts; Stripe `payment_intent.*` for settlement.
5. **Region.** Plaid production for the US/Canada pilot. A Spain pilot needs a PSD2 account-information provider instead.

## Questions for the fintech lawyer

- With Stripe Connect destination charges (or a bill-pay partner) and no Warden balance, does Warden need its own money-transmitter licenses, or does it operate under the processor's?
- What authorization must the account owner give for ACH debits initiated on their behalf and released by a family member (Nacha rules, Reg E)?
- What does the elder's consent need to say, and how should it be recorded, when an adult child gains visibility and approval rights? Today it is versioned (`CONSENT_TEXT_VERSION`) and append-only.
- What if the elder's capacity changes (power of attorney, guardianship)? The product currently assumes the elder consents for themselves.
- Data obligations for holding bank transaction data (GLBA, state privacy laws) and Plaid's end-user terms.
