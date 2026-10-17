import type { Metadata } from "next";

import { LEGAL_UPDATED } from "@/lib/legal";

export const metadata: Metadata = { title: "Licenses · Warden" };

const SOFTWARE = [
  ["Next.js", "MIT"],
  ["React, React DOM", "MIT"],
  ["Zustand", "MIT"],
  ["FastAPI", "MIT"],
  ["Pydantic, pydantic-settings", "MIT"],
  ["SQLAlchemy, Alembic", "MIT"],
  ["Uvicorn", "BSD-3-Clause"],
  ["HTTPX", "BSD-3-Clause"],
  ["asyncpg", "Apache-2.0"],
  ["cryptography", "Apache-2.0 or BSD-3-Clause"],
  ["Anthropic Python SDK", "MIT"],
  ["plaid-python", "MIT"],
  ["stripe-python", "MIT"],
  ["LiteLLM", "MIT"],
  ["pgvector-python", "MIT"],
  ["Celery", "BSD-3-Clause"],
  ["redis-py", "MIT"],
  ["email-validator", "Unlicense"],
  ["python-dotenv", "BSD-3-Clause"],
];

export default function LicensesPage() {
  return (
    <>
      <h1>Licenses and credits</h1>
      <p className="updated">Last updated {LEGAL_UPDATED}</p>

      <h2>Fonts</h2>
      <ul>
        <li>
          <b>Space Grotesk</b> by Florian Karsten — SIL Open Font License 1.1.
        </li>
        <li>
          <b>Outfit</b> by the Outfit Project Authors — SIL Open Font License 1.1.
        </li>
      </ul>
      <p>Both are served from our own site (bundled at build time), as the license allows.</p>

      <h2>Artwork and icons</h2>
      <ul>
        <li>The Warden characters (Milo, Warden, Sentinel and the rest of the cast) are original artwork made for Warden, drawn in code.</li>
        <li>
          Interface icons are simple line drawings made for Warden; some follow the shapes of Feather Icons (MIT License, © Cole
          Bemis).
        </li>
        <li>Warden uses no stock photos or third-party images.</li>
      </ul>

      <h2>Open-source software</h2>
      <p>Warden is built with these open-source projects, each used under its license:</p>
      <table>
        <thead>
          <tr>
            <th>Project</th>
            <th>License</th>
          </tr>
        </thead>
        <tbody>
          {SOFTWARE.map(([name, license]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{license}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        The full license texts ship with each package. Copyright in each project stays with its authors. The repository&apos;s
        THIRD_PARTY_NOTICES.md lists the same.
      </p>
    </>
  );
}
