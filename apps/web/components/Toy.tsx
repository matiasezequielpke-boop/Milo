import { useId } from "react";

// The cast's soft collectible characters, ported from the prototype's
// toy() generator. Blind-box proportions (chunky body, stubby feet, face
// set low) with a plush finish. Every string below is a constant — no
// user input ever reaches this markup.

export type ToyKind =
  | "beacon"
  | "lens"
  | "envelope"
  | "calc"
  | "paper"
  | "parcel"
  | "lock"
  | "mug"
  | "stamp"
  | "blob"
  | "star";

const EYE = "#3F2C22";
const PATCH = "#F8EDDC";

const TONE: Record<string, [string, string]> = {
  terracotta: ["#D68E68", "#B25F3C"],
  clay: ["#C87C5E", "#A05335"],
  rose: ["#E0AB9D", "#BE7F6E"],
  sand: ["#E3C795", "#C29B60"],
  oat: ["#EDDFC8", "#CDB894"],
  slate: ["#A8B7C2", "#7E929F"],
  sage: ["#B2BEA5", "#8A9A7C"],
  taupe: ["#C0AA97", "#9C8570"],
  ochre: ["#DDB275", "#BC8C48"],
  plum: ["#BDA2B4", "#96798D"],
  // worn only by agents the family makes, so none is mistaken for the cast
  teal: ["#A4C9C2", "#73A099"],
  lavender: ["#BEB6DA", "#9087B8"],
  peach: ["#F0BB98", "#CC8C64"],
  moss: ["#B6C795", "#889C63"],
  sky: ["#AECBE2", "#7FA2BE"],
};

const OWN_TONE: Partial<Record<ToyKind, keyof typeof TONE>> = {
  lens: "teal",
  envelope: "lavender",
  calc: "peach",
  paper: "sky",
  parcel: "moss",
};

type Tone = [string, string];

/* two bead eyes + one small stitched smile, set low on the body */
function face(cx: number, cy: number, s: number, mood?: "flat") {
  const r = 3.4 * s;
  const ex = 8.4 * s;
  const my = cy + 8.2 * s;
  const mouth =
    mood === "flat"
      ? `<path d="M${cx - 4.8 * s} ${my} h${9.6 * s}" stroke="${EYE}" stroke-width="${2 * s}" stroke-linecap="round" fill="none"/>`
      : `<path d="M${cx - 5.4 * s} ${my - 1.8 * s} q${5.4 * s} ${5.2 * s} ${10.8 * s} 0" stroke="${EYE}" stroke-width="${2 * s}" stroke-linecap="round" fill="none"/>`;
  return `<ellipse cx="${cx - ex}" cy="${cy}" rx="${r}" ry="${r * 1.14}" fill="${EYE}"/>
    <ellipse cx="${cx + ex}" cy="${cy}" rx="${r}" ry="${r * 1.14}" fill="${EYE}"/>
    <circle cx="${cx - ex - 1.1 * s}" cy="${cy - 1.5 * s}" r="${1.05 * s}" fill="#fff" opacity=".9"/>
    <circle cx="${cx + ex - 1.1 * s}" cy="${cy - 1.5 * s}" r="${1.05 * s}" fill="#fff" opacity=".9"/>
    ${mouth}`;
}

/* stubby feet + nub arms, the way a small plush sits */
const feet = (t: Tone, y = 90, dx = 13) =>
  `<ellipse cx="${50 - dx}" cy="${y}" rx="8.2" ry="5.4" fill="${t[1]}"/><ellipse cx="${50 + dx}" cy="${y}" rx="8.2" ry="5.4" fill="${t[1]}"/>`;
const arms = (t: Tone, y = 64, dx = 32) =>
  `<ellipse cx="${50 - dx}" cy="${y}" rx="6.4" ry="8.2" fill="${t[1]}"/><ellipse cx="${50 + dx}" cy="${y}" rx="6.4" ry="8.2" fill="${t[1]}"/>`;

type Spec = { t: keyof typeof TONE; f: [number, number, number]; mood?: "flat"; b: (t: Tone, g: string) => string };

const SPEC: Record<ToyKind, Spec> = {
  /* Milo — the little lighthouse the others steer by */
  beacon: {
    t: "terracotta",
    f: [50, 60, 0.92],
    b: (t, g) => `
      <ellipse cx="50" cy="22" rx="26" ry="20" fill="#FFD9A8" opacity=".35"/>
      <ellipse cx="50" cy="11" rx="17" ry="6" fill="${t[1]}"/>
      <rect x="39" y="13" width="22" height="17" rx="8" fill="${PATCH}"/>
      <rect x="31" y="28" width="38" height="7" rx="3.5" fill="${t[1]}"/>
      ${feet(t, 92, 14)}${arms(t, 64, 32)}
      <path d="M37 40q0-10 9-10h8q9 0 9 10L73 78q1 12-11 12H38q-12 0-11-12Z" fill="url(#${g})"/>
      <path d="M28.5 74h43q.6 5 .6 9H27.9q0-4 .6-9Z" fill="${PATCH}" opacity=".85"/>`,
  },
  /* Scout — the magnifying glass that goes looking */
  lens: {
    t: "slate",
    f: [50, 54, 0.95],
    b: (t, g) => `
      <rect x="61" y="62" width="18" height="36" rx="9" transform="rotate(-34 70 80)" fill="${t[1]}"/>
      ${feet(t, 91, 12)}${arms(t, 58, 32)}
      <ellipse cx="50" cy="50" rx="34" ry="33" fill="url(#${g})"/>
      <ellipse cx="50" cy="52" rx="24" ry="23" fill="${PATCH}"/>
      <path d="M34 42q5-8 13-11" stroke="#fff" stroke-width="4" stroke-linecap="round" fill="none" opacity=".75"/>`,
  },
  /* Herald — the envelope that carries word out */
  envelope: {
    t: "rose",
    f: [50, 62, 0.92],
    b: (t, g) => `
      ${feet(t, 90, 13)}${arms(t, 62, 33)}
      <rect x="15" y="24" width="70" height="62" rx="24" fill="url(#${g})"/>
      <path d="M15 44q0-20 20-20h30q20 0 20 20v1L50 68z" fill="${t[1]}"/>
      <path d="M15 45L50 69 85 45" stroke="${PATCH}" stroke-width="2.6" fill="none" stroke-linejoin="round" opacity=".8"/>`,
  },
  /* Ledger — the calculator that keeps the numbers */
  calc: {
    t: "sage",
    f: [50, 47, 0.82],
    b: (t, g) => `
      ${feet(t, 91, 13)}${arms(t, 60, 31)}
      <rect x="19" y="18" width="62" height="70" rx="22" fill="url(#${g})"/>
      <rect x="28" y="30" width="44" height="32" rx="13" fill="${PATCH}"/>
      <g fill="${PATCH}" opacity=".8">
        <circle cx="37" cy="70" r="3.4"/><circle cx="50" cy="70" r="3.4"/><circle cx="63" cy="70" r="3.4"/>
        <circle cx="37" cy="79" r="3.4"/><circle cx="50" cy="79" r="3.4"/><circle cx="63" cy="79" r="3.4"/>
      </g>`,
  },
  /* Scribe — the notebook that writes it all down */
  paper: {
    t: "oat",
    f: [50, 58, 0.95],
    b: (t, g) => `
      ${feet(t, 90, 13)}${arms(t, 60, 31)}
      <rect x="20" y="18" width="60" height="70" rx="22" fill="url(#${g})"/>
      <rect x="20" y="18" width="60" height="16" rx="8" fill="#C08A63"/>
      <rect x="33" y="76" width="34" height="5" rx="2.5" fill="#C08A63" opacity=".4"/>`,
  },
  /* Courier — the little parcel that gets it there */
  parcel: {
    t: "ochre",
    f: [50, 64, 0.92],
    b: (t, g) => `
      ${feet(t, 91, 13)}${arms(t, 62, 32)}
      <rect x="17" y="24" width="66" height="64" rx="22" fill="url(#${g})"/>
      <rect x="44" y="24" width="12" height="64" fill="${PATCH}" opacity=".85"/>
      <rect x="17" y="42" width="66" height="11" fill="${PATCH}" opacity=".85"/>`,
  },
  /* Warden — the padlock that only ever says wait */
  lock: {
    t: "taupe",
    f: [50, 66, 0.92],
    mood: "flat",
    b: (t, g) => `
      <path d="M33 48V37a17 17 0 0 1 34 0v11" fill="none" stroke="${t[1]}" stroke-width="11" stroke-linecap="round"/>
      ${feet(t, 92, 13)}${arms(t, 66, 31)}
      <rect x="18" y="44" width="64" height="48" rx="21" fill="url(#${g})"/>`,
  },
  mug: {
    t: "clay",
    f: [50, 60, 0.92],
    b: (t, g) => `
      <path d="M78 46a13 13 0 0 1 0 22" fill="none" stroke="${t[1]}" stroke-width="10" stroke-linecap="round"/>
      ${feet(t, 89, 12)}${arms(t, 60, 28)}
      <path d="M22 34q0-10 10-10h36q10 0 10 10v30q0 22-28 22t-28-22z" fill="url(#${g})"/>
      <ellipse cx="50" cy="34" rx="28" ry="8" fill="${PATCH}" opacity=".75"/>`,
  },
  stamp: {
    t: "plum",
    f: [50, 66, 0.84],
    b: (t, g) => `
      <rect x="42" y="20" width="16" height="30" rx="8" fill="${t[1]}"/>
      <ellipse cx="50" cy="18" rx="16" ry="8" fill="${t[1]}"/>
      ${feet(t, 92, 13)}${arms(t, 66, 29)}
      <rect x="14" y="46" width="72" height="44" rx="19" fill="url(#${g})"/>
      <rect x="22" y="82" width="56" height="5" rx="2.5" fill="${PATCH}" opacity=".5"/>`,
  },
  blob: {
    t: "sand",
    f: [50, 58, 1],
    b: (t, g) => `
      ${feet(t, 90, 13)}${arms(t, 58, 32)}
      <rect x="16" y="18" width="68" height="70" rx="30" fill="url(#${g})"/>`,
  },
  /* Sentinel — the beacon light that keeps watch */
  star: {
    t: "ochre",
    f: [50, 58, 0.92],
    b: (t, g) => `
      ${feet(t, 91, 13)}${arms(t, 58, 32)}
      <path d="M50 14c5 20 11 26 31 31-20 5-26 11-31 31-5-20-11-26-31-31 20-5 26-11 31-31z" fill="url(#${g})"/>
      <ellipse cx="50" cy="52" rx="22" ry="21" fill="${PATCH}" opacity=".55"/>`,
  },
};

function toySvg(kind: ToyKind, id: string, own: boolean, moodOverride?: "flat") {
  const c = SPEC[kind] ?? SPEC.blob;
  const g = `g${id}`;
  const t = TONE[(own && OWN_TONE[kind]) || c.t];
  const [fx, fy, fs] = c.f;
  const body = c.b(t, g);
  return `<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
    <defs>
      <radialGradient id="${g}" cx=".36" cy=".26" r=".92">
        <stop offset="0" stop-color="${t[0]}"/><stop offset="1" stop-color="${t[1]}"/></radialGradient>
      <filter id="f${id}" x="-25%" y="-25%" width="150%" height="150%"><feGaussianBlur stdDeviation="1.7"/></filter>
      <filter id="h${id}" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5"/></filter>
    </defs>
    <g filter="url(#f${id})" opacity=".38" transform="translate(50 58) scale(1.045) translate(-50 -58)">${body}</g>
    ${body}
    <ellipse cx="38" cy="34" rx="15" ry="11" fill="#fff" opacity=".2" filter="url(#h${id})"/>
    ${face(fx, fy, fs, moodOverride ?? c.mood)}
  </svg>`;
}

/** Decorative by default (the agent's name is always written next to it).
 *  Pass `label` where the picture stands on its own, and `own` for an
 *  agent the family made (its own colors). */
export function Toy({
  kind,
  className = "toy",
  status,
  style,
  label,
  own = false,
}: {
  kind: ToyKind;
  className?: string;
  status?: "live" | "idle" | "busy";
  style?: React.CSSProperties;
  label?: string;
  own?: boolean;
}) {
  // SVG ids must be unique per instance; useId is stable across SSR/CSR.
  const id = `t${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <span className={className} style={style} {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}>
      <span style={{ display: "block", width: "100%", height: "100%" }} dangerouslySetInnerHTML={{ __html: toySvg(kind, id, own) }} />
      {status && <span className={`st ${status}`} />}
    </span>
  );
}
