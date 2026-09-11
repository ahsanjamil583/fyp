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
        "surface-purple": "#FAF8FF",

        // ---- Borders ----------------------------------------------------------
        line: "#E5E9F3", // --border
        "line-soft": "#EEF1F7", // --border-soft

        // ---- Brand ------------------------------------------------------------
        brand: {
          DEFAULT: "#6D28D9", // --primary
          bright: "#7C3AED", // --primary-bright
          hover: "#5B21B6", // --primary-hover
          50: "#F3E8FF", // --primary-light
          100: "#EDE9FE", // --primary-soft
          200: "#DDD6FE",
          300: "#C4B5FD",
          400: "#A78BFA",
          500: "#7C3AED",
          600: "#6D28D9",
          700: "#5B21B6",
          800: "#4C1D95",
          900: "#3B1578",
        },
        primary: {
          DEFAULT: "#6D28D9",
          dark: "#5B21B6",
        },

        // ---- Sidebar ----------------------------------------------------------
        sidebar: {
          top: "#11152F",
          mid: "#151638",
          bottom: "#0B1530",
          card: "#1C2345",
          text: "#D8DDF2",
          muted: "#929AB8",
          "active-start": "#6541D8",
          "active-end": "#742DF2",
          hover: "rgba(255, 255, 255, 0.06)",
        },

        // ---- AI / purple ------------------------------------------------------
        purple: {
          DEFAULT: "#6C20F6",
          glow: "#A477FF",
          50: "#F6F1FF",
          100: "#EEE7FF", // --purple-light
          200: "#DFD1FF",
          300: "#C6ADFF",
          400: "#A477FF",
          500: "#8B4CFA",
          600: "#6C20F6",
          700: "#5A16D0",
          800: "#4A14AB",
          900: "#3C1187",
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

        // ---- Green / success --------------------------------------------------
        green: {
          DEFAULT: "#10B968",
          50: "#E6F9F0", // --green-light
          100: "#CFF3E1",
          200: "#A3E8C6",
          300: "#6FDAA6",
          400: "#37C985",
          500: "#10B968",
          600: "#059653", // --green-dark
          700: "#047C45",
          800: "#046237",
          900: "#03502E",
        },
        // Plenty of pages reach for emerald-*; keep it a synonym of the success ramp
        // rather than leaving a second, off-scheme green in the UI.
        emerald: {
          DEFAULT: "#10B968",
          50: "#E6F9F0",
          100: "#CFF3E1",
          200: "#A3E8C6",
          300: "#6FDAA6",
          400: "#37C985",
          500: "#10B968",
          600: "#059653",
          700: "#047C45",
          800: "#046237",
          900: "#03502E",
        },
        accent: "#10B968",

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
        "sidebar-rail": "linear-gradient(180deg, #11152F 0%, #151638 45%, #0B1530 100%)",
        "sidebar-active": "linear-gradient(90deg, #6541D8 0%, #742DF2 100%)",
        cta: "linear-gradient(90deg, #6D28D9, #7C3AED)",
        "ai-card": "linear-gradient(135deg, #25145F 0%, #352080 45%, #241452 100%)",
      },

      boxShadow: {
        card: "0 4px 18px rgba(16, 22, 51, 0.04)",
        soft: "0 4px 18px rgba(16, 22, 51, 0.04)",
        lift: "0 10px 30px rgba(16, 22, 51, 0.08)",
        "nav-active": "0 6px 18px rgba(109, 40, 217, 0.35)",
        brand: "0 6px 18px rgba(109, 40, 217, 0.35)",
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
