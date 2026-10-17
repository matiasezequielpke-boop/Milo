"use client";

import { useEffect } from "react";

import { Toy } from "@/components/Toy";
import { CAST } from "@/lib/agents";
import { useApp } from "@/lib/store";

export default function CastPage() {
  const setCrumb = useApp((s) => s.setCrumb);
  const openSheet = useApp((s) => s.openSheet);
  const live = CAST.filter((a) => a.live).length;

  useEffect(() => setCrumb("Your agents", `${live} live`), [setCrumb, live]);

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
    </div>
  );
}
