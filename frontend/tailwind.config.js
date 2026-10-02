/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Fintech dark palette: deep slate surfaces, teal accent, semantic
        // risk colors shared by every chart and component.
        surface: {
          950: "#050a14",
          900: "#0a1220",
          850: "#0e1829",
          800: "#13203a",
          700: "#1b2c4d",
        },
        accent: {
          DEFAULT: "#2dd4bf",
          dim: "#14b8a6",
        },
        "risk-high": "#f43f5e",
        "risk-med": "#f59e0b",
        "risk-low": "#10b981",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
