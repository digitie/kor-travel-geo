import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--ui-background)",
        foreground: "var(--ui-foreground)",
        card: {
          DEFAULT: "var(--ui-card)",
          foreground: "var(--ui-card-foreground)"
        },
        popover: {
          DEFAULT: "var(--ui-popover)",
          foreground: "var(--ui-popover-foreground)"
        },
        primary: {
          DEFAULT: "var(--ui-primary)",
          foreground: "var(--ui-primary-foreground)"
        },
        secondary: {
          DEFAULT: "var(--ui-secondary)",
          foreground: "var(--ui-secondary-foreground)"
        },
        accent: {
          DEFAULT: "var(--ui-accent)",
          foreground: "var(--ui-accent-foreground)"
        },
        destructive: "var(--ui-destructive)",
        border: "var(--ui-border)",
        input: "var(--ui-input)",
        ring: "var(--ui-ring)",
        text: {
          strong: "var(--text-strong)",
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          disabled: "var(--text-disabled)"
        },
        surface: {
          page: "var(--surface-page)",
          card: "var(--surface-card)",
          subtle: "var(--surface-subtle)",
          muted: "var(--surface-muted)",
          row: "var(--surface-row)"
        },
        ink: "#172033",
        muted: {
          DEFAULT: "var(--ui-muted)",
          foreground: "var(--ui-muted-foreground)"
        },
        line: "#d8dee8",
        panel: "#f7f9fc",
        brand: "#0f766e",
        "brand-tint": "var(--brand-tint)",
        info: "#1d4ed8",
        success: "var(--ok)",
        warn: "#b45309",
        danger: "#b42318"
      }
    }
  },
  plugins: []
};

export default config;
