import type { Metadata } from "next";
import Link from "next/link";

import { BUSINESS, LEGAL_UPDATED } from "@/lib/legal";

export const metadata: Metadata = { title: "Privacy Policy · Warden" };

export default function PrivacyPage() {
  return (
    <>
      <h1>Privacy Policy</h1>
      <p className="updated">Last updated {LEGAL_UPDATED}</p>
      <div className="box glass">
        <p style={{ margin: 0 }}>
          <b>The short version.</b> Warden reads a person&apos;s bank activity (through Plaid) to spot scams and odd charges, and only
          pays or cancels something after a family member they chose says yes. We don&apos;t sell your data, we don&apos;t show ads, and
          we don&apos;t use analytics trackers. You can download or delete your data from Settings at any time.
        </p>
      </div>
      <p>
        This policy explains what {BUSINESS.name === "Warden" ? "Warden" : `${BUSINESS.name} ("Warden")`} (&quot;we&quot;) collects when you use the Warden website and app, why,
        who we share it with, and the choices you have. It was written to match how the product works today and will be reviewed by
        counsel before Warden launches publicly.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>
          <b>Your account:</b> your email address and a password. The password is checked and stored (hashed) by our sign-in provider,
          Supabase; it passes through our server when you log in but we never store or log it. We also keep a record of when you agreed
          to our Terms, confirmed you&apos;re 18 or older, and the version of the text you agreed to.
        </li>
        <li>
          <b>Your family set-up:</b> the names and emails of people you invite, everyone&apos;s role (account owner or family approver),
          and what the account owner allowed each approver to do — including when they changed it.
        </li>
        <li>
          <b>Bank information, if the account owner connects a bank:</b> account names, the last digits of account numbers, balances and
          up to two years of transactions (amount, date, description, merchant, category). This comes from Plaid. We never see or store
          the bank username or password.
        </li>
        <li>
          <b>What you add or do in Warden:</b> bills you record, chat messages with Milo, payment and cancellation requests, approvals and
          blocks, and how you resolved alerts.
        </li>
        <li>
          <b>Sign-in security records:</b> the email and time of each sign-in attempt, used to stop password guessing, and the sessions
          you&apos;re signed in with. Warden doesn&apos;t store IP addresses or device fingerprints; our hosting providers keep standard
          server logs for a short time.
        </li>
        <li>
          <b>On your device:</b> a few items in your browser&apos;s storage to keep you signed in and remember your settings. See the{" "}
          <Link href="/cookies">Cookie Policy</Link>. We don&apos;t use cookies for advertising or analytics.
        </li>
      </ul>
      <p>We only ask for what the service needs. You don&apos;t have to give us a phone number, address, date of birth or ID.</p>

      <h2>How we use it</h2>
      <ul>
        <li>To run the service: watch for suspicious charges, recurring payments and bills; answer questions in chat; ask the family to approve payments or cancellations; and carry out what was approved.</li>
        <li>To keep accounts secure: the two-step login (password, then a code we email you), rate limits, and the activity log.</li>
        <li>To send you service emails: sign-in codes, approval requests, alerts and outcomes. You can turn off everything except sign-in codes.</li>
      </ul>
      <p>
        We don&apos;t sell personal information, share it for cross-context behavioral advertising, or use it to build marketing profiles. We
        don&apos;t train AI models on your data.
      </p>

      <h2>Who we share it with</h2>
      <p>Only the providers that make Warden work, each for its own part, and the family members the account owner chooses:</p>
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>What for</th>
            <th>What it gets</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Supabase</td>
            <td>Sign-in and our database</td>
            <td>Your email and password (hashed); the data described above, stored on our behalf</td>
          </tr>
          <tr>
            <td>Plaid</td>
            <td>Connecting the bank (read-only)</td>
            <td>
              What you enter in Plaid&apos;s window. Plaid&apos;s{" "}
              <a href="https://plaid.com/legal/#end-user-privacy-policy" target="_blank" rel="noopener noreferrer">
                End User Privacy Policy
              </a>{" "}
              applies.
            </td>
          </tr>
          <tr>
            <td>Anthropic</td>
            <td>The AI (Claude) behind the chat</td>
            <td>Your chat messages and the account details needed to answer them, under commercial terms that don&apos;t allow training on this data</td>
          </tr>
          <tr>
            <td>Stripe</td>
            <td>Making approved payments</td>
            <td>The payee, amount and reference of each approved payment</td>
          </tr>
          <tr>
            <td>Resend</td>
            <td>Sending notification emails</td>
            <td>Your email address and the message</td>
          </tr>
          <tr>
            <td>Vercel</td>
            <td>Hosting this website</td>
            <td>Standard web request data needed to serve pages</td>
          </tr>
        </tbody>
      </table>
      <p>
        <b>Family members:</b> an approver sees only what the account owner allows (accounts, alerts, approving payments), and the owner
        can change or remove that at any time. Everyone in a family sees the shared activity log.
      </p>
      <p>We may also disclose information if the law requires it, or to protect someone from fraud or harm.</p>

      <h2>How long we keep it</h2>
      <ul>
        <li>Account, family and bank data: while the account is open.</li>
        <li>Sign-in attempt records: up to 30 days.</li>
        <li>
          When you delete your account we delete your data from our live database straight away and remove the bank connection at Plaid.
          Copies in our providers&apos; backups are overwritten on their own schedule.
        </li>
        <li>
          If you were a family approver, the account owner&apos;s activity log keeps your name next to decisions you made, because the owner
          needs that record of who approved what.
        </li>
      </ul>

      <h2>Your choices and rights</h2>
      <ul>
        <li><b>Download your data:</b> Settings → Download your data.</li>
        <li><b>Delete your account:</b> Settings → Delete your account.</li>
        <li><b>Stop notification emails:</b> the link at the bottom of any email, or Settings.</li>
        <li><b>Change what a family member can see:</b> Family (account owners only).</li>
        <li>
          <b>US state privacy rights</b> (such as California&apos;s): you can ask to know, correct or delete your personal information, and we
          won&apos;t treat you differently for asking. We don&apos;t sell or share personal information.
        </li>
        <li>
          <b>If you&apos;re in the EU or UK:</b> we rely on our contract with you to run the service, the account owner&apos;s consent for
          sharing with family, and our legitimate interest in security. You can access, correct, delete, export or object to processing,
          and complain to your data protection authority.
        </li>
      </ul>

      <h2>Children</h2>
      <p>
        Warden is only for adults (18+). We don&apos;t knowingly collect information from anyone under 18. If you think a child has given
        us information, contact us and we&apos;ll delete it.
      </p>

      <h2>Security</h2>
      <p>
        Logging in takes your password and a code we email you. Bank access tokens are stored encrypted. Nothing that moves money happens
        without a family approver&apos;s yes, and every request and decision is recorded. No system is perfectly secure; if something goes
        wrong that affects you, we&apos;ll tell you.
      </p>

      <h2>Where data is processed</h2>
      <p>Our providers may store and process data in the United States and other countries, with safeguards required by law.</p>

      <h2>Changes</h2>
      <p>If we change this policy in a way that matters, we&apos;ll tell you in the app or by email before it takes effect.</p>
    </>
  );
}
