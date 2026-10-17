import Link from "next/link";

import { BusinessDetails, LegalLinks } from "@/components/Legal";
import { Toy } from "@/components/Toy";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="ambient" aria-hidden="true">
        <i className="b1" />
        <i className="b2" />
        <i className="b3" />
        <i className="b4" />
      </div>
      <a className="skip" href="#doc">
        Skip to content
      </a>
      <div className="doc">
        <article>
          <div className="top">
            <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Toy kind="beacon" />
              <b>Warden</b>
            </Link>
            <span className="sp" />
            <Link className="bt g sm" href="/">
              Back to Warden
            </Link>
          </div>
          <main id="doc">{children}</main>
          <h2>Who runs Warden</h2>
          <BusinessDetails />
          <LegalLinks className="legal" />
        </article>
      </div>
    </>
  );
}
