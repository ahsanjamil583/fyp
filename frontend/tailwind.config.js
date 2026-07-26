/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        muted: "#667085",
        line: "#E5E7EB",
        surface: "#F7F8FA",
        brand: "#2563EB",
        accent: "#10B981"
      },
      boxShadow: {
        soft: "0 10px 30px rgba(23, 32, 51, 0.08)"
      }
    },
  },
  plugins: [],
};
