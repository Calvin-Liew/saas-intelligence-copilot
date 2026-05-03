/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        muted: "#667085",
        line: "#d9dee8",
        panel: "#f7f9fc",
        accent: "#2563eb",
        teal: "#0f766e",
        amber: "#b45309",
      },
      boxShadow: {
        soft: "0 16px 40px rgba(23, 32, 51, 0.08)",
      },
    },
  },
  plugins: [],
};
