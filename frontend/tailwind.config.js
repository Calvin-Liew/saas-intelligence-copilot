/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--color-canvas) / <alpha-value>)",
        surface: "hsl(var(--color-surface) / <alpha-value>)",
        ink: "hsl(var(--color-ink) / <alpha-value>)",
        muted: "hsl(var(--color-muted) / <alpha-value>)",
        line: "hsl(var(--color-line) / <alpha-value>)",
        panel: "hsl(var(--color-panel) / <alpha-value>)",
        accent: "hsl(var(--color-accent) / <alpha-value>)",
        "accent-hover": "hsl(var(--color-accent-hover) / <alpha-value>)",
        signal: "hsl(var(--color-signal) / <alpha-value>)",
        amber: "hsl(var(--color-amber) / <alpha-value>)",
        danger: "hsl(var(--color-danger) / <alpha-value>)",
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
      },
      borderRadius: {
        ds: "var(--radius-md)",
        "ds-lg": "var(--radius-lg)",
      },
    },
  },
  plugins: [],
};
