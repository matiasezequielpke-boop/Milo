import type { ReactNode } from "react";

// Line icons in the prototype's style: 24-unit grid, round caps, stroke 2.
function Icon({ children, w = 2 }: { children: ReactNode; w?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export const IconPlus = () => (
  <Icon w={2.2}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);
export const IconSearch = () => (
  <Icon>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4-4" />
  </Icon>
);
export const IconChats = () => (
  <Icon>
    <path d="M4 6h16M4 12h16M4 18h10" />
  </Icon>
);
export const IconApprovals = () => (
  <Icon>
    <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" />
    <path d="m9 12 2 2 4-4" />
  </Icon>
);
export const IconAlert = () => (
  <Icon>
    <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9" />
    <path d="M10.3 20a1.9 1.9 0 0 0 3.4 0" />
  </Icon>
);
export const IconMoney = () => (
  <Icon>
    <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </Icon>
);
export const IconFamily = () => (
  <Icon>
    <circle cx="9" cy="8" r="3" />
    <circle cx="17" cy="10" r="2.6" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0M13.5 20a4.6 4.6 0 0 1 8-3" />
  </Icon>
);
export const IconActivity = () => (
  <Icon>
    <path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
  </Icon>
);
export const IconMoon = () => (
  <Icon>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icon>
);
export const IconSun = () => (
  <Icon>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
);
export const IconMore = () => (
  <Icon>
    <circle cx="12" cy="12" r="1.7" />
    <circle cx="19" cy="12" r="1.7" />
    <circle cx="5" cy="12" r="1.7" />
  </Icon>
);
export const IconMenu = () => (
  <Icon>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Icon>
);
export const IconSend = () => (
  <Icon w={2.4}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </Icon>
);
export const IconInfo = () => (
  <Icon>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5M12 16h.01" />
  </Icon>
);
export const IconCheck = () => (
  <Icon w={2.6}>
    <path d="M20 6 9 17l-5-5" />
  </Icon>
);
export const IconClock = () => (
  <Icon>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);
export const IconLock = () => (
  <Icon>
    <rect x="5" y="11" width="14" height="10" rx="3" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Icon>
);
export const IconModel = () => (
  <Icon>
    <circle cx="12" cy="12" r="3.2" />
    <path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1M18.4 18.4l-2.1-2.1M7.7 7.7 5.6 5.6" />
  </Icon>
);
export const IconSwap = () => (
  <Icon>
    <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
  </Icon>
);
export const IconBank = () => (
  <Icon>
    <path d="M3 10 12 4l9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18" />
  </Icon>
);
export const IconWarn = () => (
  <Icon>
    <path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 17h.01" />
  </Icon>
);
export const IconLogout = () => (
  <Icon>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11" />
  </Icon>
);
export const IconDownload = () => (
  <Icon>
    <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />
  </Icon>
);
