import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const PYTHON_VWORLD_KEY = "KTG_VWORLD_API_KEY";
const UI_VWORLD_KEY = "NEXT_PUBLIC_VWORLD_API_KEY";
const PYTHON_DAGSTER_URL_KEY = "KTG_DAGSTER_PUBLIC_URL";
const UI_DAGSTER_URL_KEY = "NEXT_PUBLIC_DAGSTER_URL";

type RuntimeEnv = Partial<NodeJS.ProcessEnv>;

export function resolveVWorldApiKey(
  env: RuntimeEnv = process.env,
  cwd?: string
): string {
  return (
    normalizeEnvValue(env[PYTHON_VWORLD_KEY]) ||
    readDotenvKey(PYTHON_VWORLD_KEY, cwd) ||
    normalizeEnvValue(env[UI_VWORLD_KEY]) ||
    readDotenvKey(UI_VWORLD_KEY, cwd)
  );
}

// The browser-facing Dagster UI URL (geo-dagster public domain). Resolved the same
// way as the VWorld key so an operator sets it once in the backend .env; empty ->
// the admin Dagster embed hides itself gracefully. NOT used for backend GraphQL
// (that stays internal `dagster_url`, SSRF-allowlisted).
export function resolveDagsterPublicUrl(
  env: RuntimeEnv = process.env,
  cwd?: string
): string {
  return (
    normalizeEnvValue(env[PYTHON_DAGSTER_URL_KEY]) ||
    readDotenvKey(PYTHON_DAGSTER_URL_KEY, cwd) ||
    normalizeEnvValue(env[UI_DAGSTER_URL_KEY]) ||
    readDotenvKey(UI_DAGSTER_URL_KEY, cwd)
  );
}

function readDotenvKey(key: string, cwd?: string): string {
  const candidates = cwd
    ? [join(cwd, "..", ".env"), join(cwd, ".env"), join(cwd, ".env.local")]
    : [
        join(/*turbopackIgnore: true*/ process.cwd(), "..", ".env"),
        join(/*turbopackIgnore: true*/ process.cwd(), ".env"),
        join(/*turbopackIgnore: true*/ process.cwd(), ".env.local")
      ];
  for (const path of candidates) {
    if (!existsSync(path)) continue;
    const value = parseDotenvValue(readFileSync(path, "utf8"), key);
    if (value) return value;
  }
  return "";
}

export function parseDotenvValue(contents: string, key: string): string {
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator < 1) continue;
    if (line.slice(0, separator).trim() !== key) continue;
    return normalizeEnvValue(line.slice(separator + 1));
  }
  return "";
}

function normalizeEnvValue(value: string | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}
