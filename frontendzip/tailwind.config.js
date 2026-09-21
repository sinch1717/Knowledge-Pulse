/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#F2EDE3",
          raised: "#FBF8F1",
          sunk: "#EAE3D5",
        },
        ink: {
          DEFAULT: "#16130F",
          soft: "#4A4238",
          faint: "#8B8171",
        },
        rule: {
          DEFAULT: "#DDD5C6",
          strong: "#C7BCA6",
        },
        oxblood: {
          DEFAULT: "#7A2E2E",
          deep: "#5C2020",
          wash: "#F0E2DE",
        },
        olive: {
          DEFAULT: "#5A6337",
          wash: "#E7E8D8",
        },
        ochre: {
          DEFAULT: "#A87C2A",
          wash: "#F3E9D2",
        },
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        // Type scale, roughly a minor third
        micro: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        small: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.6rem" }],
        lead: ["1.0625rem", { lineHeight: "1.75rem" }],
        h3: ["1.25rem", { lineHeight: "1.6rem" }],
        h2: ["1.75rem", { lineHeight: "2.1rem" }],
        h1: ["2.5rem", { lineHeight: "2.7rem" }],
        display: ["3.5rem", { lineHeight: "3.4rem" }],
      },
      borderRadius: {
        sm: "2px",
        DEFAULT: "3px",
        md: "5px",
      },
      maxWidth: {
        measure: "68ch",
      },
    },
  },
  plugins: [],
};
