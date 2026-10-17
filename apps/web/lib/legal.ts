// Legal pages and the consent a new account gives. When Terms or Privacy
// change materially, bump LEGAL_VERSION here and LEGAL_VERSION in the API
// (app/config.py) so each account records which text it agreed to.
export const LEGAL_VERSION = "2026-10-17";
export const LEGAL_UPDATED = "October 17, 2026";

// Business details. Set these in the web app's environment once the
// company is incorporated; until then the pages say so instead of
// showing made-up details.
export const BUSINESS = {
  name: process.env.NEXT_PUBLIC_BUSINESS_NAME || "Warden",
  address: process.env.NEXT_PUBLIC_BUSINESS_ADDRESS || null,
  email: process.env.NEXT_PUBLIC_CONTACT_EMAIL || null,
};

export const LEGAL_LINKS = [
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
  { href: "/cookies", label: "Cookies" },
  { href: "/refunds", label: "Refunds" },
  { href: "/licenses", label: "Licenses" },
];
