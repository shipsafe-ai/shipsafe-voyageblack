import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0A0A0B",
          surface: "#111113",
          elevated: "#18181B",
          overlay: "#1E1E22",
        },
        border: {
          subtle: "#27272A",
          DEFAULT: "#3F3F46",
          strong: "#52525B",
        },
        text: {
          primary: "#FAFAFA",
          secondary: "#A1A1AA",
          tertiary: "#71717A",
          disabled: "#52525B",
        },
        accent: "#3B82F6",
        signal: {
          block: "#EF4444",
          warn: "#F59E0B",
          approve: "#22C55E",
          info: "#3B82F6",
        },
      },
      fontFamily: {
        sans: ["Geist", "system-ui", "sans-serif"],
        mono: ["DM Mono", "Fira Code", "monospace"],
      },
      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "4px",
        md: "4px",
        lg: "4px",
      },
    },
  },
  plugins: [],
};
export default config;
