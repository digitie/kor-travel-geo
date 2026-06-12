import coreWebVitals from "eslint-config-next/core-web-vitals";

export default [
  ...coreWebVitals,
  {
    ignores: [".next/**", "node_modules/**", "types/api.gen.ts", "lib/schemas.gen.ts"],
    rules: {
      "import/no-anonymous-default-export": "off",
      "react-hooks/set-state-in-effect": "off"
    }
  }
];
