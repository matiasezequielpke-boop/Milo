import type { Metadata } from "next";

import { LEGAL_UPDATED } from "@/lib/legal";

export const metadata: Metadata = { title: "Refund Policy · Warden" };

export default function RefundsPage() {
  return (
    <>
      <h1>Refund Policy</h1>
      <p className="updated">Last updated {LEGAL_UPDATED}</p>

      <h2>Warden itself is free right now</h2>
      <p>
        During the pilot we don&apos;t charge for Warden and we don&apos;t take a fee from payments it makes. There&apos;s nothing to refund, and
        no card is needed to sign up.
      </p>

      <h2>Payments Warden makes for you</h2>
      <ul>
        <li>Warden only pays a bill after a family approver says yes, and pays exactly the payee and amount that were approved.</li>
        <li>
          If a payment turns out to be wrong — a duplicate, the wrong amount, or a bill you didn&apos;t owe — the refund comes from the company
          that received it. We&apos;ll give you the payment details and help you ask for it.
        </li>
        <li>If a payment fails, no money moves and you can ask again.</li>
        <li>During the demo and pilot, payments run in test mode and no real money moves at all.</li>
      </ul>

      <h2>If we introduce paid plans</h2>
      <p>
        We&apos;ll update this page and tell you at least 30 days before charging anything. You&apos;ll see the price before you choose a plan,
        you&apos;ll be able to cancel at any time from Settings as easily as you signed up, and this page will say exactly when you can get
        your money back.
      </p>
    </>
  );
}
