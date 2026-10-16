import type { Config } from "tailwindcss";

// Warden console: monochrome, chat-first, no ornament (the Grok-like
// direction). Colour is reserved for meaning only — red for fraud/block,
// amber for "needs a look", green for "done". Type runs large because
// half the people reading it are in their 70s.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#000000",
          900: "#0a0a0a",
          850: "#111111",
          800: "#161616",
          700: "#1f1f1f",
          600: "#2a2a2a",
        },
      },
      fontSize: {
        base: ["1.0625rem", { lineHeight: "1.6" }],
      },
      maxWidth: {
        chat: "46rem",
      },
    },
  },
  plugins: [],
};

export default config;
