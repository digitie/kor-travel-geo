#!/usr/bin/env node
// vworld-map-web (inside the maplibre-vworld-react tarball dep) builds under
// TypeScript's NodeNext module resolution, which requires explicit `.js`
// extensions on relative import/export specifiers even though the files are
// `.ts`/`.tsx` — Node's own ESM loader resolves those `.js` names against the
// package's *compiled* `dist/` output, where they're real files.
//
// This app deliberately bypasses that `dist/` build entirely and points
// Turbopack/webpack (see next.config.mjs) directly at vworld-map-web's `.ts`/
// `.tsx` *source* instead, to avoid pulling in the full package barrel (see
// lib/vworld.ts's header comment). Turbopack transpiles that source itself
// and has no NodeNext-style ".js resolves to a same-named .ts sibling" logic
// for it (confirmed: `experimental.extensionAlias`, webpack's equivalent
// knob, is on Next's documented list of options Turbopack does not
// implement) — so every relative `from "./foo.js"` fails to resolve, since
// no literal `foo.js` file exists next to `foo.ts` in source form.
//
// Fix: after each `npm install`, strip the `.js` suffix back off relative
// import/export specifiers in the installed copy of vworld-map-web's source,
// so Turbopack's normal extensionless resolution (which already tries
// `.tsx`/`.ts`) finds them. Idempotent — re-running is a no-op once patched.
//
// Uses a manual recursive walk instead of `fs.promises.glob` — that API only
// exists from Node 22 onward, but this project's CI runs Node 20 (ADR-019).
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageDir = path.join(__dirname, "..", "node_modules", "maplibre-vworld-react");
const targetDir = path.join(packageDir, "packages", "vworld-map-web", "src");

// Matches `from "./foo.js"` / `from '../bar/baz.js'` in both `import ... from`
// and `export ... from` statements. Relative specifiers only (`./`, `../`) —
// never touches bare package specifiers like `from "maplibre-gl"`.
const RELATIVE_JS_IMPORT_RE = /(from\s+["'])(\.\.?\/[^"']+)\.js(["'])/g;
const SOURCE_FILE_RE = /\.(ts|tsx)$/;

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(entryPath);
    } else if (entry.isFile() && SOURCE_FILE_RE.test(entry.name)) {
      yield entryPath;
    }
  }
}

function main() {
  if (!existsSync(packageDir)) {
    // Genuinely not installed in this context (e.g. a package.json that
    // doesn't depend on maplibre-vworld-react at all) — a real no-op, not an
    // error.
    console.log("[patch-vworld-map-web-esm-imports] maplibre-vworld-react not installed, skipping");
    return;
  }
  if (!existsSync(targetDir)) {
    // The package IS installed but its expected internal layout isn't there —
    // this is the one caller of this script (kor-travel-geo-ui's own
    // postinstall) and it always expects this subpath to exist, so silently
    // doing nothing here would just defer the real failure to a much less
    // direct "Module not found" further into `npm run build`/`type-check`.
    console.error(
      `[patch-vworld-map-web-esm-imports] maplibre-vworld-react is installed but ${targetDir} does not exist — upstream package layout may have changed, this script needs updating`
    );
    process.exitCode = 1;
    return;
  }

  let patchedCount = 0;
  let scannedCount = 0;
  for (const filePath of walk(targetDir)) {
    scannedCount += 1;
    const original = readFileSync(filePath, "utf8");
    const patched = original.replace(RELATIVE_JS_IMPORT_RE, "$1$2$3");
    if (patched !== original) {
      writeFileSync(filePath, patched, "utf8");
      patchedCount += 1;
    }
  }
  console.log(
    `[patch-vworld-map-web-esm-imports] patched ${patchedCount}/${scannedCount} file(s)`
  );
}

main();
