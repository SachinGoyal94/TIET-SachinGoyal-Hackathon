/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#030810",
          900: "#060d18",
          850: "#0a1422",
          800: "#0e1a2e",
          700: "#16263f",
          600: "#1e3050",
        },
        accent: {
          DEFAULT: "#00e5b0",
          dim: "#00c9a0",
          bright: "#5effd4",
        },
        "risk-high": "#ff4757",
        "risk-med": "#ffa502",
        "risk-low": "#2ed573",
        gain: "#00e5b0",
        loss: "#ff4757",
        muted: "#3e5a80",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "ticker-scroll": "ticker 40s linear infinite",
        "glow": "glow 2s ease-in-out infinite alternate",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        ticker: {
          "0%": { transform: "translateX(0%)" },
          "100%": { transform: "translateX(-50%)" },
        },
        glow: {
          "0%": { boxShadow: "0 0 5px rgba(0,229,176,0.2)" },
          "100%": { boxShadow: "0 0 20px rgba(0,229,176,0.4)" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.03)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
        glow: "0 0 20px rgba(0,229,176,0.15), inset 0 0 20px rgba(0,229,176,0.03)",
      },
    },
  },
  plugins: [],
};
