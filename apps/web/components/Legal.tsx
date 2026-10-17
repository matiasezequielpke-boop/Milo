import Link from "next/link";

import { BUSINESS, LEGAL_LINKS } from "@/lib/legal";

export function LegalLinks({ className = "legal-links" }: { className?: string }) {
  return (
    <nav className={className} aria-label="Legal">
      {LEGAL_LINKS.map((l) => (
        <Link key={l.href} href={l.href}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}

/** Who runs Warden and how to reach them — only what's actually set. */
export function BusinessDetails() {
  return (
    <ul>
      <li>
        <b>{BUSINESS.name}</b>
        {!BUSINESS.address && " — the company is being incorporated; its legal name and registered address will be listed here before launch."}
      </li>
      {BUSINESS.address && <li>Registered address: {BUSINESS.address}</li>}
      <li>
        Contact:{" "}
        {BUSINESS.email ? (
          <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>
        ) : (
          "a support address will be published here before launch. Account holders can export or delete their data at any time from Settings."
        )}
      </li>
    </ul>
  );
}
