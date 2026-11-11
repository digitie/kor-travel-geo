import assert from "node:assert/strict";
import { ESLint } from "eslint";

const eslint = new ESLint();
// 실제 코드 진단으로 설정 이관 시 Next·Hooks·접근성·React 검사가 사라지지 않게 한다.
const probes = [
  {
    source: 'window.location.assign("/login");',
    rule: "@next/next/no-location-assign-relative-destination",
  },
  {
    source: 'export default function Probe() { return <script src="https://example.org/script.js" />; }',
    rule: "@next/next/no-sync-scripts",
  },
  {
    source: 'import { useState } from "react"; export function Probe({ enabled }: { enabled: boolean }) { if (enabled) useState(0); return null; }',
    rule: "react-hooks/rules-of-hooks",
  },
  {
    source: 'export function Probe() { return <div aria-made-up="true" />; }',
    rule: "jsx-a11y-x/aria-props",
  },
  {
    source: 'export function Probe() { return <img src="/example.png" />; }',
    rule: "jsx-a11y-x/alt-text",
  },
  {
    source: 'export function Probe() { return [1, 2].map(value => <span>{value}</span>); }',
    rule: "react-x/no-missing-key",
  },
  {
    source: 'export function Probe() { return <div dangerouslySetInnerHTML={{ __html: "example" }}>child</div>; }',
    rule: "react-dom/no-dangerously-set-innerhtml-with-children",
  },
];

await Promise.all(probes.map(async ({ source, rule }) => {
  const [result] = await eslint.lintText(source, { filePath: "components/eslint-coverage-probe.tsx" });
  assert(result.messages.some(message => message.ruleId === rule), `검사 누락: ${rule}`);
}));
console.log(`ESLint 실제 진단 ${probes.length}개 확인`);
