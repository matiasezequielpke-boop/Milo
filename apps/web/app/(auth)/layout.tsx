"use client";

import { useEffect } from "react";

import { LegalLinks } from "@/components/Legal";
import { Toy } from "@/components/Toy";
import { BUSINESS } from "@/lib/legal";
import { useApp } from "@/lib/store";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const status = useApp((s) => s.status);
  useEffect(() => {
    if (status === "loading") void useApp.getState().load();
  }, [status]);

  return (
    <>
      <div className="ambient" aria-hidden="true">
        <i className="b1" />
        <i className="b2" />
        <i className="b3" />
        <i className="b4" />
      </div>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="auth">
        <main id="main">
          <div className="brandrow">
            <Toy kind="beacon" />
            <b>Warden</b>
          </div>
          {children}
        </main>
        <footer>
          <LegalLinks className="" />
          <span>
            © {new Date().getFullYear()} {BUSINESS.name}
          </span>
        </footer>
      </div>
    </>
  );
}
