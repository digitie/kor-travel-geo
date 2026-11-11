import { defineConfig, globalIgnores } from "eslint/config";
import nextPlugin from "@next/eslint-plugin-next";
import { createTypeScriptImportResolver } from "eslint-import-resolver-typescript";
import importX from "eslint-plugin-import-x";
import jsxA11y from "eslint-plugin-jsx-a11y-x";
import reactDom from "eslint-plugin-react-dom";
import reactHooks from "eslint-plugin-react-hooks";
import reactX from "eslint-plugin-react-x";
import tseslint from "typescript-eslint";

const hooksConfig = reactHooks.configs.flat["recommended-latest"];
// 중복 Hooks 진단은 공식 플러그인이 담당한다. react-x의 나머지 권장 규칙은 유지한다.
const reactRules = Object.fromEntries(
  Object.entries(reactX.configs.recommended.rules).filter(
    ([name]) => !Object.hasOwn(hooksConfig.rules, name.replace("react-x/", "react-hooks/"))
  )
);

export default defineConfig([
  ...tseslint.configs.recommended,
  importX.flatConfigs.recommended,
  {
    // Next의 location 규칙은 선언된 브라우저 전역 참조만 검사한다.
    languageOptions: { globals: { window: "readonly", document: "readonly", location: "readonly", self: "readonly" } },
    settings: {
      "import-x/resolver-next": [
        createTypeScriptImportResolver({ alwaysTryTypes: true, project: "./tsconfig.json" }),
      ],
    },
  },
  { ...reactX.configs.recommended, rules: reactRules },
  reactDom.configs.recommended,
  hooksConfig,
  nextPlugin.configs.recommended,
  nextPlugin.configs["core-web-vitals"],
  {
    plugins: { "jsx-a11y-x": jsxA11y },
    rules: {
      // 기존 Next 접근성 검사와 Image 대체 텍스트 검사를 그대로 유지한다.
      "jsx-a11y-x/alt-text": ["warn", { elements: ["img"], img: ["Image"] }],
      "jsx-a11y-x/aria-props": "warn",
      "jsx-a11y-x/aria-proptypes": "warn",
      "jsx-a11y-x/aria-unsupported-elements": "warn",
      "jsx-a11y-x/role-has-required-aria-props": "warn",
      "jsx-a11y-x/role-supports-aria-props": "warn",
      // 기존 예외: Compiler 미사용 환경에서 외부 상태와 동기화하는 effect를 허용한다.
      // rules-of-hooks/exhaustive-deps 및 나머지 Compiler 진단은 계속 검사한다.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([
    ".next/**", "out/**", "build/**", "next-env.d.ts",
    "types/api.gen.ts", "lib/schemas.gen.ts",
  ]),
]);
