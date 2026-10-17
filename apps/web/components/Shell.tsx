"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import {
  IconActivity,
  IconAlert,
  IconApprovals,
  IconChats,
  IconFamily,
  IconMenu,
  IconMoney,
  IconMoon,
  IconMore,
  IconPlus,
  IconSearch,
  IconSun,
  IconSwap,
} from "@/components/icons";
import { AgentSheet } from "@/components/AgentSheet";
import { Toy } from "@/components/Toy";
import { CAST } from "@/lib/agents";
import { useActiveHousehold, useApp } from "@/lib/store";

const NAV = [
  { href: "/", label: "Chats", icon: IconChats },
  { href: "/approvals", label: "Approvals", icon: IconApprovals, count: "pendingApprovals" as const },
  { href: "/alerts", label: "Alerts", icon: IconAlert, count: "openAlerts" as const },
  { href: "/money", label: "Money", icon: IconMoney },
  { href: "/family", label: "Family", icon: IconFamily },
  { href: "/activity", label: "Activity", icon: IconActivity },
];

const SEG = [
  { href: "/", label: "Chat" },
  { href: "/cast", label: "Cast" },
  { href: "/roadmap", label: "Roadmap" },
];

const ROLE_LABEL = { elder: "Account owner", approver: "Family approver" } as const;

/** The segmented control's pill rides a critically-damped-ish spring that
 *  always starts from where it is now, so a second tap mid-flight
 *  redirects it instead of restarting (the prototype's step()). */
function Seg({ pathname }: { pathname: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const s = useRef({ px: 0, pw: 0, tx: 0, tw: 0, vx: 0, vw: 0, raf: 0, placed: false });
  const active = SEG.findIndex((x) => x.href === pathname);

  useLayoutEffect(() => {
    const root = ref.current;
    const el = root?.querySelectorAll("a")[active] as HTMLElement | undefined;
    const p = pill.current;
    if (!root || !el || !p) return;
    const st = s.current;
    const paint = () => {
      p.style.transform = `translateX(${st.px}px)`;
      p.style.width = `${st.pw}px`;
    };
    const snap = () => {
      const a = root.querySelectorAll("a")[active] as HTMLElement;
      st.px = st.tx = a.offsetLeft;
      st.pw = st.tw = a.offsetWidth;
      st.vx = st.vw = 0;
      paint();
    };
    const step = () => {
      const k = 0.16;
      const d = 0.74;
      st.vx += (st.tx - st.px) * k;
      st.vx *= d;
      st.px += st.vx;
      st.vw += (st.tw - st.pw) * k;
      st.vw *= d;
      st.pw += st.vw;
      if (Math.abs(st.tx - st.px) > 0.2 || Math.abs(st.tw - st.pw) > 0.2 || Math.abs(st.vx) > 0.2) {
        paint();
        st.raf = requestAnimationFrame(step);
      } else {
        st.raf = 0;
        st.px = st.tx;
        st.pw = st.tw;
        paint();
      }
    };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!st.placed || reduce) {
      snap();
      st.placed = true;
    } else {
      st.tx = el.offsetLeft;
      st.tw = el.offsetWidth;
      if (!st.raf) st.raf = requestAnimationFrame(step);
    }
    // Web fonts change the tab widths after first paint.
    const ro = new ResizeObserver(() => {
      if (!st.raf) snap();
    });
    ro.observe(root);
    return () => ro.disconnect();
  }, [active]);

  useEffect(() => () => cancelAnimationFrame(s.current.raf), []);

  return (
    <nav className="seg" ref={ref} aria-label="Views">
      <span className="pill" ref={pill} />
      {SEG.map((x, i) => (
        <Link key={x.href} href={x.href} className={i === active ? "on" : ""} aria-current={i === active ? "page" : undefined}>
          {x.label}
        </Link>
      ))}
    </nav>
  );
}

function Toast() {
  const toast = useApp((s) => s.toast);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!toast) return;
    setOn(true);
    const t = setTimeout(() => setOn(false), 3000);
    return () => clearTimeout(t);
  }, [toast]);
  return (
    <div className={`toast glass deep ${on ? "on" : ""}`} role="status" aria-live="polite">
      {toast && <Toy kind={toast.kind} />}
      <span>{toast?.text}</span>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const app = useApp();
  const household = useActiveHousehold();
  const [menu, setMenu] = useState(false);
  const [people, setPeople] = useState(false);
  const [more, setMore] = useState(false);
  const [q, setQ] = useState("");
  const [dark, setDark] = useState(true);

  useEffect(() => {
    if (app.status === "loading") void app.load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setDark(document.documentElement.getAttribute("data-theme") !== "light");
  }, []);

  // Close transient surfaces on navigation.
  useEffect(() => {
    setMenu(false);
    setMore(false);
    setPeople(false);
  }, [pathname]);

  // Popovers close on any outside press.
  useEffect(() => {
    if (!more && !people) return;
    const close = (e: PointerEvent) => {
      if (!(e.target as Element).closest(".pop, [data-pop]")) {
        setMore(false);
        setPeople(false);
      }
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMore(false);
        setPeople(false);
      }
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [more, people]);

  // Specular sheen: each glass surface catches light where the pointer is.
  useEffect(() => {
    let last: HTMLElement | null = null;
    const reset = (el: HTMLElement) => {
      el.style.setProperty("--mx", "30%");
      el.style.setProperty("--my", "0%");
      el.style.setProperty("--sheen-o", ".85");
    };
    const move = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.(".glass") as HTMLElement | null;
      if (last && last !== el) reset(last);
      last = el;
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${(((e.clientX - r.left) / r.width) * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(((e.clientY - r.top) / r.height) * 100).toFixed(1)}%`);
      el.style.setProperty("--sheen-o", "1");
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => document.removeEventListener("pointermove", move);
  }, []);

  function toggleTheme() {
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem("warden.theme", next);
    } catch {
      /* not persisted; fine */
    }
    setDark(!dark);
  }

  function newTask() {
    app.setConversation(null);
    setMore(false);
    if (pathname !== "/") router.push("/");
    setTimeout(() => document.getElementById("prompt")?.focus(), 60);
  }

  const counts = { pendingApprovals: app.pendingApprovals, openAlerts: app.openAlerts };
  const ready = app.status === "ready";
  const me = app.people.find((p) => p.email === app.me?.email);
  const other = app.people.find((p) => p.email !== app.me?.email);
  const canApprove = Boolean(household?.my_scopes.includes("approve_actions"));
  const needle = q.trim().toLowerCase();
  const match = (s: string) => !needle || s.toLowerCase().includes(needle);
  const liveAgents = CAST.filter((a) => a.live);
  const agentStatus = (id: string) =>
    !ready ? "idle" : id === "milo" && !app.integrations?.model ? "idle" : id === "warden" && app.pendingApprovals > 0 ? "busy" : "live";
  const showSeg = SEG.some((x) => x.href === pathname);

  return (
    <>
      <div className="ambient" aria-hidden="true">
        <i className="b1" />
        <i className="b2" />
        <i className="b3" />
        <i className="b4" />
      </div>

      <div className="shell">
        <aside className={`side glass ${menu ? "on" : ""}`} aria-label="Sidebar">
          <div className="brand">
            <Toy kind="beacon" className="logo" />
            <div>
              <b>
                Milo
                <span
                  className="demoBadge"
                  title="Demo: no sign-in, a test bank (Plaid sandbox) and test payments (Stripe test mode). Replies come from the live model, not a script."
                >
                  Demo
                </span>
              </b>
              <span className="tag">The trust layer for your money</span>
            </div>
          </div>

          <button className="cta" onClick={newTask}>
            <IconPlus />
            New task
          </button>

          <div className="find">
            <IconSearch />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats & agents" aria-label="Search chats and agents" />
          </div>

          <div className="sscroll">
            <div className="grp">
              <div className="h">
                <span>Workspace</span>
              </div>
              {NAV.map((item) => {
                const on = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                const count = item.count ? counts[item.count] : 0;
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href} className={`row ${on ? "on" : ""}`} aria-current={on ? "page" : undefined}>
                    <Icon />
                    <span className="t">{item.label}</span>
                    {count > 0 && (
                      <span className="cnt" aria-label={`${count} waiting`}>
                        {count}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>

            <div className="grp">
              <div className="h">
                <span>Agents</span>
              </div>
              {liveAgents
                .filter((a) => match(a.name) || match(a.role))
                .map((a) => (
                  <button key={a.id} className={`row ${app.sheet === a.id ? "on" : ""}`} onClick={() => app.openSheet(a.id)}>
                    <Toy kind={a.kind} status={agentStatus(a.id)} />
                    <span className="nm">
                      <b>{a.name}</b>
                      <span>{a.role}</span>
                    </span>
                  </button>
                ))}
            </div>

            {app.conversations.length > 0 && (
              <div className="grp">
                <div className="h">
                  <span>Recent</span>
                </div>
                {app.conversations
                  .filter((c) => match(c.title || "Chat"))
                  .slice(0, 12)
                  .map((c) => (
                    <button
                      key={c.id}
                      className={`row ${pathname === "/" && app.activeConversation === c.id ? "on" : ""}`}
                      onClick={() => {
                        app.setConversation(c.id);
                        if (pathname !== "/") router.push("/");
                        setMenu(false);
                      }}
                    >
                      <span className="t dim">{c.title || "Chat"}</span>
                    </button>
                  ))}
              </div>
            )}
          </div>

          <div style={{ position: "relative" }}>
            <div className={`pop glass deep up ${people ? "on" : ""}`} role="menu" aria-label="View as">
              <div className="ph">Demo · view as</div>
              {app.people.map((p) => (
                <button
                  key={p.email}
                  role="menuitemradio"
                  aria-checked={p.email === app.me?.email}
                  className={`pi ${p.email === app.me?.email ? "on" : ""}`}
                  onClick={() => {
                    setPeople(false);
                    void app.switchPerson(p.email);
                  }}
                >
                  <span className="av">{p.name[0]}</span>
                  <span className="nm">
                    <b>{p.name}</b>
                    <span>{ROLE_LABEL[p.role]}</span>
                  </span>
                </button>
              ))}
            </div>
            <button
              className="me"
              data-pop
              onClick={() => ready && setPeople((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={people}
              disabled={!ready}
              style={!ready ? { opacity: 1, cursor: "default" } : undefined}
            >
              <span className="av">{me ? me.name[0] : <PersonGlyph />}</span>
              <span className="nm">
                <b>{me ? `Viewing as ${me.name}` : "Demo family"}</b>
                <span>{me ? ROLE_LABEL[me.role] : ready ? "" : app.status === "loading" ? "Connecting…" : "Not connected"}</span>
              </span>
              {ready && <IconSwap />}
            </button>
          </div>
        </aside>

        <div className="main">
          <header className={`chrome glass ${showSeg ? "has-seg" : ""}`}>
            <button className="gbtn mob" aria-label="Open menu" aria-expanded={menu} onClick={() => setMenu((v) => !v)}>
              <IconMenu />
            </button>
            <div className="crumb">
              <b>{app.crumb.title}</b>
              {app.crumb.sub && ` · ${app.crumb.sub}`}
            </div>
            <div className="sp" />
            {showSeg && <Seg pathname={pathname} />}
            {ready && canApprove && app.pendingApprovals > 0 && pathname !== "/approvals" && (
              <Link className="cta sm" href="/approvals">
                <IconApprovals />
                <span className="lbl">
                  Review {app.pendingApprovals} {app.pendingApprovals === 1 ? "approval" : "approvals"}
                </span>
              </Link>
            )}
            <button className="gbtn" onClick={toggleTheme} aria-label={dark ? "Switch to light appearance" : "Switch to dark appearance"} title="Appearance">
              {dark ? <IconSun /> : <IconMoon />}
            </button>
            <button className="gbtn" data-pop onClick={() => setMore((v) => !v)} aria-label="More" aria-haspopup="menu" aria-expanded={more}>
              <IconMore />
            </button>
          </header>
          <div className={`pop glass deep top ${more ? "on" : ""}`} role="menu" aria-label="More">
            <button className="pi" role="menuitem" onClick={newTask}>
              <IconPlus />
              New task
            </button>
            {ready && other && (
              <button
                className="pi"
                role="menuitem"
                onClick={() => {
                  setMore(false);
                  void app.switchPerson(other.email);
                }}
              >
                <IconSwap />
                View as {other.name}
              </button>
            )}
            <hr />
            <Link className="pi" role="menuitem" href="/activity">
              <IconActivity />
              Activity log
            </Link>
          </div>
          <main className="pane" id="pane">
            {children}
          </main>
        </div>
      </div>

      <div className={`veil ${menu ? "on" : ""}`} onClick={() => setMenu(false)} aria-hidden="true" />
      <AgentSheet agentId={app.sheet} onClose={() => app.openSheet(null)} />
      <Toast />
    </>
  );
}

function PersonGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </svg>
  );
}
