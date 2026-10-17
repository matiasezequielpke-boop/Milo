import type { Metadata } from "next";
import Link from "next/link";

import { BUSINESS, LEGAL_UPDATED } from "@/lib/legal";

export const metadata: Metadata = { title: "Terms of Service · Warden" };

export default function TermsPage() {
  return (
    <>
      <h1>Terms of Service</h1>
      <p className="updated">Last updated {LEGAL_UPDATED}</p>
      <p>
        These terms are the agreement between you and {BUSINESS.name === "Warden" ? "Warden" : `${BUSINESS.name} ("Warden")`} (&quot;we&quot;) for using Warden. By creating
        an account you agree to them and to our <Link href="/privacy">Privacy Policy</Link>. They will be reviewed by counsel before
        Warden launches publicly.
      </p>

      <h2>1. Who can use Warden</h2>
      <p>You must be 18 or older and able to agree to these terms. One person per account; don&apos;t share your login.</p>

      <h2>2. What Warden does — and doesn&apos;t</h2>
      <ul>
        <li>Warden reads bank activity you connect (read-only, through Plaid), points out charges that look like scams or mistakes, and keeps track of bills and subscriptions.</li>
        <li>It can prepare a payment or a cancellation, but nothing is paid or cancelled until a family approver chosen by the account owner says yes.</li>
        <li>
          Warden is <b>not a bank</b>, doesn&apos;t hold your money, and doesn&apos;t give financial, legal or tax advice. Payments are carried out
          by licensed payment providers.
        </li>
        <li>
          Milo, the chat assistant, uses AI. It can be wrong. Check the payee and amount before approving anything — what you approve is
          what gets paid.
        </li>
        <li>Alerts can miss things or flag things that turn out to be fine. If you suspect fraud, also call your bank.</li>
      </ul>

      <h2>3. Families and consent</h2>
      <p>
        The account owner decides what each family approver can see and do, and can change or take it back at any time. Approvers agree to
        use that access only to help the account owner, and the account owner can always block a request.
      </p>

      <h2>4. Your account</h2>
      <p>
        Keep your password and sign-in codes private. Tell us straight away if you think someone else got into your account. You&apos;re
        responsible for what happens in your account, except where it&apos;s our fault.
      </p>

      <h2>5. Bank connections and payments</h2>
      <ul>
        <li>Bank connections go through Plaid; its terms and privacy policy also apply to that step.</li>
        <li>
          During the demo and pilot, payments run in test mode and move no real money. When real payments are switched on we&apos;ll update
          these terms and ask you to agree again.
        </li>
        <li>Payments go to the payee you approved, for the amount you approved. Disputes about the bill itself are between you and the payee; we&apos;ll help where we can.</li>
      </ul>

      <h2>6. Fees</h2>
      <p>
        Warden is free during the pilot. We don&apos;t add fees to payments it makes. If we introduce paid plans, we&apos;ll show the price up front,
        tell you at least 30 days before anything changes, and only charge you if you choose a plan. See the{" "}
        <Link href="/refunds">Refund Policy</Link>.
      </p>

      <h2>7. Acceptable use</h2>
      <p>
        Don&apos;t use Warden to access accounts you&apos;re not allowed to, to pressure or exploit anyone, to break the law, or to interfere with the
        service or other people&apos;s data.
      </p>

      <h2>8. Ending your account</h2>
      <p>
        You can delete your account at any time from Settings. We may suspend or close an account that breaks these terms or puts others at
        risk, and we&apos;ll tell you why unless the law or safety prevents it.
      </p>

      <h2>9. Disclaimers and limits</h2>
      <p>
        We work hard to keep Warden accurate and available, but it&apos;s provided &quot;as is&quot; during the pilot, without guarantees that
        it will catch every problem or always be available. To the extent the law allows, we&apos;re not liable for indirect or consequential
        losses. Nothing in these terms limits rights you have by law that can&apos;t be limited.
      </p>

      <h2>10. Changes to these terms</h2>
      <p>
        If we change these terms in a way that matters, we&apos;ll tell you in the app or by email before the change takes effect. If you
        don&apos;t agree, you can delete your account.
      </p>

      <h2>11. Governing law</h2>
      <p>The governing law and venue will be stated here once Warden&apos;s company is incorporated, before public launch.</p>

      <h2>12. Contact</h2>
      <p>See &quot;Who runs Warden&quot; below.</p>
    </>
  );
}
