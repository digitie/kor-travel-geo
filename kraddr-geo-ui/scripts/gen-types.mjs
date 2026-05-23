import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(root, "..");
const backendOpenApi = resolve(appRoot, "..", "openapi.json");
const typesOut = resolve(appRoot, "types", "api.gen.ts");
const schemasOut = resolve(appRoot, "lib", "schemas.gen.ts");
const openapiTypescriptCli = resolve(appRoot, "node_modules", "openapi-typescript", "bin", "cli.js");

execFileSync(
  process.execPath,
  [openapiTypescriptCli, backendOpenApi, "-o", typesOut],
  { cwd: appRoot, stdio: "inherit" }
);

const openapi = JSON.parse(readFileSync(backendOpenApi, "utf8"));
const names = Object.keys(openapi.components?.schemas ?? {}).sort();
writeFileSync(
  schemasOut,
  [
    "// openapi.json에서 생성된 schema 이름 목록. 런타임 Zod mirror는 lib/schemas.ts에서 관리한다.",
    `export const apiSchemaNames = ${JSON.stringify(names, null, 2)} as const;`,
    ""
  ].join("\n")
);
