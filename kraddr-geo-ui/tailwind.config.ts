import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        muted: "#667085",
        line: "#d8dee8",
        panel: "#f7f9fc",
        brand: "#0f766e",
        info: "#1d4ed8",
        warn: "#b45309",
        danger: "#b42318"
      }
    }
  },
  plugins: []
};

export default config;
