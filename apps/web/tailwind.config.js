/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Google brand palette
        brand: {
          DEFAULT: "var(--primary)",
          50: "var(--info-soft)",
          100: "var(--info-soft)",
          200: "var(--accent-soft)",
          300: "#a8c7fa",
          400: "#8ab4f8",
          500: "var(--primary)",
          600: "var(--primary-hover)",
          700: "var(--primary-active)",
          800: "var(--primary-ink)",
          900: "var(--primary-ink)",
        },
        // Google four colors (charts / accents)
        g: {
          blue: "#4285f4",
          red: "#ea4335",
          yellow: "#fbbc05",
          green: "#34a853",
          deep: "#0043ad",
        },
        // Semantic surfaces
        surface: {
          DEFAULT: "var(--background)",
          alt: "var(--background-alt)",
          card: "var(--card)",
          muted: "var(--muted)",
          border: "var(--border)",
        },
        ink: {
          DEFAULT: "var(--foreground)",
          muted: "var(--foreground-muted)",
          subtle: "var(--foreground-subtle)",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-dm-sans)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "Noto Sans SC",
          "sans-serif",
        ],
        mono: [
          "var(--font-jetbrains)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "1.4" }],
        xs: ["11px", { lineHeight: "1.45" }],
        sm: ["13px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.55" }],
        md: ["15px", { lineHeight: "1.55" }],
        lg: ["16px", { lineHeight: "1.5" }],
        xl: ["18px", { lineHeight: "1.4" }],
        "2xl": ["20px", { lineHeight: "1.35" }],
        "3xl": ["24px", { lineHeight: "1.25" }],
        "4xl": ["30px", { lineHeight: "1.2" }],
        "5xl": ["36px", { lineHeight: "1.15" }],
        "6xl": ["48px", { lineHeight: "1.05" }],
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        none: "none",
        xs: "var(--shadow-sm)",
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        brand: "var(--shadow-brand)",
        focus: "var(--shadow-focus)",
      },
      transitionTimingFunction: {
        DEFAULT: "var(--ease)",
        google: "var(--ease)",
      },
      transitionDuration: {
        DEFAULT: "var(--dur-base)",
        fast: "var(--dur-fast)",
        base: "var(--dur-base)",
        slow: "var(--dur-slow)",
      },
      spacing: {
        sidebar: "var(--sidebar-width)",
        "sidebar-collapsed": "var(--sidebar-collapsed)",
        "header-h": "var(--header-height)",
      },
      keyframes: {
        "google-fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "google-slide-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "google-pulse-dot": {
          "0%, 100%": { transform: "scale(1)", opacity: "1" },
          "50%": { transform: "scale(1.4)", opacity: "0.4" },
        },
        "google-shimmer": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "google-spin": {
          to: { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "fade-in": "google-fade-in var(--dur-slow) var(--ease) both",
        "slide-up": "google-slide-up var(--dur-slow) var(--ease) both",
        "pulse-dot": "google-pulse-dot 1.4s var(--ease) infinite",
        shimmer: "google-shimmer 1.4s linear infinite",
        spin: "google-spin 1s linear infinite",
      },
    },
  },
  plugins: [],
};
