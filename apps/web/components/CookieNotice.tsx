"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const KEY = "warden.cookieNotice";

/** Warden sets no cookies and runs no analytics or ads: it only keeps what
 *  it needs in this browser (sign-in, appearance). Nothing needs consent,
 *  so this is a notice, not a consent wall. If optional storage is ever
 *  added, it must ask first — with "No" as easy as "Yes". */
export function CookieNotice() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      setShow(window.localStorage.getItem(KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);
  if (!show) return null;
  return (
    <section className="cookie glass deep" aria-label="Cookie notice">
      <p>
        Warden doesn&apos;t use advertising or analytics cookies. It only stores what it needs on this device to keep you signed in
        and remember your settings.
      </p>
      <div className="acts">
        <button
          className="bt p sm"
          onClick={() => {
            try {
              window.localStorage.setItem(KEY, "1");
            } catch {
              /* shows again next visit */
            }
            setShow(false);
          }}
        >
          OK
        </button>
        <Link href="/cookies">Cookie policy</Link>
      </div>
    </section>
  );
}
