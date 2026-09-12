/** @type {import('tailwindcss').Config} */

// The palette is the design system from the brief, expressed through the token names the
// app already used. Retheming is therefore a change of values rather than a rewrite of
// every className. The semantic ramps (green / amber / red / purple / blue / slate) are
// overridden on purpose: hundreds of existing status pills reference them by shade, so
// re-pointing the ramp moves the whole app onto the scheme in one place. Each ramp keeps
// a full 50-900 range so no existing shade can resolve to nothing.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // ---- Typography -------------------------------------------------------
        ink: "#101633", // --text-primary
        muted: "#52638D", // --text-secondary
        subtle: "#8490AE", // --text-muted

        // ---- Surfaces ---------------------------------------------------------
        page: "#F8FAFF", // --page-bg
        // NOTE: `surface` stays the soft tint rather than --surface (#FFFFFF). Existing
        // code uses `bg-surface` for inset blocks *inside* white cards; pointing it at
        // pure white would make those blocks disappear. Pure white is `bg-white`.
        surface: "#F8F9FD", // --surface-soft
        "surface-purple": "#F0F7FF",

        // ---- Borders ----------------------------------------------------------
        line: "#E5E9F3", // --border
        "line-soft": "#EEF1F7", // --border-soft

        // ---- Brand ------------------------------------------------------------
        brand: {
          DEFAULT: "#2563EB", // --primary
          bright: "#38BDF8", // --primary-bright
          hover: "#1D4ED8", // --primary-hover
          50: "#EFF6FF", // --primary-light
          100: "#DBEAFE", // --primary-soft
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
        },
        primary: {
          DEFAULT: "#2563EB",
          dark: "#1D4ED8",
        },

        // ---- Sidebar ----------------------------------------------------------
        sidebar: {
          top: "#102A43",
          mid: "#123047",
          bottom: "#081827",
          card: "#173954",
          text: "#DCE9F5",
          muted: "#9CB4CA",
          "active-start": "#1D4ED8",
          "active-end": "#2563EB",
          hover: "rgba(255, 255, 255, 0.06)",
        },

        // ---- AI accents mapped into the blue system ---------------------------
        purple: {
          DEFAULT: "#2563EB",
          glow: "#38BDF8",
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
        },

        // ---- Blue -------------------------------------------------------------
        blue: {
          DEFAULT: "#1677FF",
          50: "#EAF3FF", // --blue-light
          100: "#D6E8FF",
          200: "#AFD2FF",
          300: "#7FB5FF",
          400: "#4B96FF",
          500: "#1677FF",
          600: "#0F5FD6",
          700: "#0C4BAB",
          800: "#0B3D8A",
          900: "#0A3370",
        },

        // ---- Blue success/info aliases ----------------------------------------
        green: {
          DEFAULT: "#2563EB",
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
        },
        // Plenty of pages reach for emerald-*; keep it a synonym of the blue ramp
        // rather than leaving a second, off-scheme green in the UI.
        emerald: {
          DEFAULT: "#2563EB",
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
        },
        accent: "#2563EB",

        // ---- Orange / warning -------------------------------------------------
        orange: {
          DEFAULT: "#FF9800",
          50: "#FFF8EC",
          100: "#FFF3DF", // --orange-light
          200: "#FFE2B5",
          300: "#FFCD85",
          400: "#FFB44D",
          500: "#FF9800",
          600: "#E98500",
          700: "#C06D00",
          800: "#99570A",
          900: "#7C4711",
        },
        amber: {
          DEFAULT: "#FF9800",
          50: "#FFF8EC",
          100: "#FFF3DF",
          200: "#FFE2B5",
          300: "#FFCD85",
          400: "#FFB44D",
          500: "#FF9800",
          600: "#E98500",
          700: "#C06D00",
          800: "#99570A",
          900: "#7C4711",
        },

        // ---- Red / danger -----------------------------------------------------
        red: {
          DEFAULT: "#EF4444",
          50: "#FEECEC", // --danger-light
          100: "#FDDCDC",
          200: "#FBBDBD",
          300: "#F79595",
          400: "#F26C6C",
          500: "#EF4444",
          600: "#DC2626",
          700: "#B91C1C",
          800: "#991B1B",
          900: "#7F1D1D",
        },

        // ---- Neutrals ---------------------------------------------------------
        // Re-pointed at the scheme's text/border colours so the many slate-* usages
        // read as navy rather than the stock grey-blue.
        slate: {
          50: "#F8F9FD",
          100: "#EEF1F7",
          200: "#E5E9F3",
          300: "#CBD3E4",
          400: "#8490AE",
          500: "#6E7B9C",
          600: "#52638D",
          700: "#3C4B72",
          800: "#263252",
          900: "#101633",
          950: "#0B1530",
        },
      },

      backgroundImage: {
        "sidebar-rail": "linear-gradient(180deg, #102A43 0%, #123047 45%, #081827 100%)",
        "sidebar-active": "linear-gradient(90deg, #1D4ED8 0%, #38BDF8 100%)",
        cta: "linear-gradient(90deg, #1D4ED8, #2563EB)",
        "ai-card": "linear-gradient(135deg, #071A3D 0%, #123047 48%, #172554 100%)",
      },

      boxShadow: {
        card: "0 4px 18px rgba(16, 22, 51, 0.04)",
        soft: "0 4px 18px rgba(16, 22, 51, 0.04)",
        lift: "0 10px 30px rgba(16, 22, 51, 0.08)",
        "nav-active": "0 6px 18px rgba(37, 99, 235, 0.28)",
        brand: "0 6px 18px rgba(37, 99, 235, 0.28)",
        rail: "0 24px 60px rgba(11, 21, 48, 0.45)",
      },

      borderRadius: {
        card: "1rem",
        rail: "0.75rem",
      },
    },
  },
  plugins: [],
};
