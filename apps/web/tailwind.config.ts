import type { Config } from "tailwindcss";

// Design tokens per claude/frontend-design-system.md (Milo v7):
// Liquid Glass material (blur + saturate + edge refraction) with a
// terracotta/orange accent instead of the typical iOS blue.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        terracotta: {
          50: "#fdf3ee",
          100: "#fbe4d8",
          200: "#f6c5ab",
          300: "#efa078",
          400: "#e67a4c",
          500: "#d9622f",
          600: "#b84c22",
          700: "#953b1c",
          800: "#78311c",
          900: "#632a1a",
        },
        ink: {
          950: "#0b0a09",
          900: "#131110",
          800: "#1c1917",
        },
      },
      backdropBlur: {
        glass: "20px",
      },
      borderRadius: {
        glass: "20px",
      },
    },
  },
  plugins: [],
};

export default config;
