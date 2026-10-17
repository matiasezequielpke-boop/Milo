import type { Metadata } from "next";

import { LEGAL_UPDATED } from "@/lib/legal";

export const metadata: Metadata = { title: "Cookie Policy · Warden" };

const ITEMS = [
  { name: "warden.session", why: "Keeps you signed in (your sign-in tokens).", kind: "Essential", until: "You log out or the session ends" },
  { name: "warden.demoEmail", why: "Which demo family member you're viewing as.", kind: "Essential (demo only)", until: "You leave the demo" },
  { name: "warden.theme", why: "Remembers light or dark appearance.", kind: "Preference", until: "You clear your browser data" },
  { name: "warden.cookieNotice", why: "Remembers that you've seen the cookie notice.", kind: "Preference", until: "You clear your browser data" },
];

export default function CookiesPage() {
  return (
    <>
      <h1>Cookie Policy</h1>
      <p className="updated">Last updated {LEGAL_UPDATED}</p>
      <p>
        Warden doesn&apos;t set cookies, and doesn&apos;t use advertising, analytics or tracking tools of any kind. It keeps a few items in your
        browser&apos;s local storage so the app works:
      </p>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>What it&apos;s for</th>
            <th>Type</th>
            <th>Kept until</th>
          </tr>
        </thead>
        <tbody>
          {ITEMS.map((i) => (
            <tr key={i.name}>
              <td>
                <code>{i.name}</code>
              </td>
              <td>{i.why}</td>
              <td>{i.kind}</td>
              <td>{i.until}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        These are needed for the service you asked for, so they don&apos;t require consent. If we ever add anything optional, we&apos;ll ask first —
        and saying no will be as easy as saying yes.
      </p>

      <h2>Other services</h2>
      <ul>
        <li>
          When you connect a bank, Plaid&apos;s window loads from Plaid and may use its own cookies or storage for security and fraud
          prevention, under Plaid&apos;s privacy policy. It only loads when you choose to connect a bank.
        </li>
        <li>Fonts are served from our own site, so loading a page doesn&apos;t contact Google or other font services.</li>
      </ul>

      <h2>Clearing it</h2>
      <p>
        Logging out removes your sign-in. You can clear everything else through your browser&apos;s settings (site data for this website).
      </p>
    </>
  );
}
