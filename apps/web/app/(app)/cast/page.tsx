"use client";

import { useEffect } from "react";

import { IconPlus } from "@/components/icons";
import { Toy } from "@/components/Toy";
import { CAST, scheduleShort } from "@/lib/agents";
import { useActiveHousehold, useApp } from "@/lib/store";

export default function CastPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  const openSheet = useApp((s) => s.openSheet);
  const custom = useApp((s) => s.customAgents);
  const ready = useApp((s) => s.status === "ready");
  const household = useActiveHousehold();
  const live = CAST.filter((a) => a.live).length;

  useEffect(
    () => setCrumb("Your agents", custom.length ? `${live} live · ${custom.length} yours` : `${live} live`),
    [setCrumb, live, custom.length],
  );

  return (
    <div className="cast">
      <span className="kicker">The fleet</span>
      <p className="lede">
        Milo leads a crew of specialists. <b>{live} are live in this demo</b>; the rest are on the way. Tap one to see what it does.
      </p>
      <div className="cgrid">
        {CAST.map((a) => (
          <button key={a.id} className={`ccard glass ${a.live ? "" : "soon"}`} onClick={() => openSheet(a.id)}>
            <div className="stage">
              <Toy kind={a.kind} />
            </div>
            <b>{a.name}</b>
            <span>{a.role}</span>
            <span className={`toylab ${a.live ? "" : "idle"}`}>
              <i />
              {a.live ? "Live" : "Coming soon"}
            </span>
          </button>
        ))}
      </div>

      {ready && household && (
        <>
          <span className="kicker sec">Yours</span>
          <p className="lede">
            Make an agent for one job — a monthly spending review, a weekly bill check. <b>It reads the accounts and reports back</b>; it
            can&apos;t move money.
          </p>
          <div className="cgrid">
            {custom.map((a) => (
              <button key={a.id} className="ccard glass" onClick={() => openSheet(a.ref)}>
                <div className="stage">
                  <Toy kind={a.kind} own />
                </div>
                <b>{a.name}</b>
                <span>{a.created_by ? `Made by ${a.created_by}` : "Made by your family"}</span>
                <span className="toylab">
                  <i />
                  {scheduleShort(a.schedule)}
                </span>
              </button>
            ))}
            <button className="ccard make" onClick={() => openSheet("new")}>
              <div className="stage">
                <IconPlus />
              </div>
              <b>Make an agent</b>
              <span>Give it a name, a face and a job</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
