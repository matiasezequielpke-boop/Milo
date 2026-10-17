"use client";

import { useEffect } from "react";

import { IconCheck, IconClock } from "@/components/icons";
import { useApp } from "@/lib/store";

const ROAD = {
  v1: {
    label: "In this demo",
    tag: "Now",
    items: [
      { t: "Family accounts with consent", d: "The parent decides what a family approver can see and do, and can take it back at any time." },
      { t: "Bank connection", d: "Read-only through Plaid. Warden sees balances and transactions; it never sees the bank password." },
      { t: "Scam & odd-charge alerts", d: "Gift cards, crypto, wires, duplicates, new subscriptions, price jumps — each with the reason why." },
      { t: "Family approval for every payment", d: "Nothing is paid or cancelled until a family approver says yes. The parent can always block." },
      { t: "Settled test payment", d: "An approved bill is paid through Stripe test mode, exactly as approved." },
      { t: "Shared activity log", d: "Every request, decision and payment, in order. Nothing can be edited or deleted." },
    ],
  },
  v2: {
    label: "Pilot",
    tag: "Next",
    items: [
      { t: "Pay from the parent's own account", d: "Bank debit through licensed partners, after legal review. Warden never holds the money." },
      { t: "Near-real-time alerts", d: "Bank webhooks instead of periodic syncs, plus text and email to the family." },
      { t: "3–5 families", d: "Real bills, real approvals, real feedback — the proof point before scaling." },
    ],
  },
  v3: {
    label: "Later",
    tag: "After the pilot",
    items: [
      { t: "Refunds & disputes", d: "Warden prepares the claim; the family approves it." },
      { t: "Bill negotiation & card renewals", d: "With the same approval gate in front of every step." },
      { t: "A version for everyone", d: "Warden for your own money, no family required." },
      { t: "Insurance", d: "Vision stage — not committed." },
    ],
  },
};

export default function RoadmapPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  useEffect(() => setCrumb("Roadmap"), [setCrumb]);

  return (
    <div className="road">
      <span className="kicker">Roadmap</span>
      <p className="lede">
        What works in this demo today, and the plan to make Warden <b>move real money safely</b> for families.
      </p>
      <div className="rcols">
        {(["v1", "v2", "v3"] as const).map((k) => (
          <section key={k} className={`rcol ${k} glass`}>
            <div className="rh">
              <span className="dot" />
              <b>{ROAD[k].label}</b>
              <span className="tag">{ROAD[k].tag}</span>
            </div>
            {ROAD[k].items.map((i) => (
              <div key={i.t} className="ritem">
                {k === "v1" ? <IconCheck /> : <IconClock />}
                <div>
                  <b>{i.t}</b>
                  {i.d}
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
