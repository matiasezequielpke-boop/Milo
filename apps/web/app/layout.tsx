import type { Metadata, Viewport } from "next";
import { Outfit, Space_Grotesk } from "next/font/google";

import { CookieNotice } from "@/components/CookieNotice";

import "./globals.css";

const outfit = Outfit({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-outfit", display: "swap" });
const space = Space_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-space", display: "swap" });

export const metadata: Metadata = {
  title: "Milo",
  description:
    "Milo — Warden, the AI agent that handles your money: watches for scams, keeps bills on track, and never pays or cancels anything without a family member's OK.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0806" },
    { media: "(prefers-color-scheme: light)", color: "#f2ede7" },
  ],
  width: "device-width",
  initialScale: 1,
};

// Applies a saved appearance before first paint so there's no flash.
const THEME_SCRIPT = `try{var t=localStorage.getItem("warden.theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${outfit.variable} ${space.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {children}
        <CookieNotice />
      </body>
    </html>
  );
}
