import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { parseDotenvValue, resolveVWorldApiKey } from "@/lib/runtime-config";

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    rmSync(dir, { force: true, recursive: true });
  }
});

describe("runtime config", () => {
  it("Python API VWorld 키가 UI 전용 키보다 우선한다", () => {
    expect(
      resolveVWorldApiKey({
        KRADDR_GEO_VWORLD_API_KEY: "python-key",
        NEXT_PUBLIC_VWORLD_API_KEY: "ui-key"
      })
    ).toBe("python-key");
  });

  it("Python API 키가 없으면 UI 전용 환경변수를 사용한다", () => {
    const root = mkdtempSync(join(tmpdir(), "kraddr-geo-ui-runtime-"));
    tempDirs.push(root);

    expect(resolveVWorldApiKey({ NEXT_PUBLIC_VWORLD_API_KEY: "ui-key" }, root)).toBe(
      "ui-key"
    );
  });

  it("Python 프로젝트 루트 .env의 VWorld API 키를 읽는다", () => {
    const root = mkdtempSync(join(tmpdir(), "kraddr-geo-ui-runtime-"));
    tempDirs.push(root);
    const uiDir = join(root, "kraddr-geo-ui");
    mkdirSync(uiDir);
    writeFileSync(
      join(root, ".env"),
      [
        "# local secrets",
        "KRADDR_GEO_JUSO_API_KEY=unused",
        "KRADDR_GEO_VWORLD_API_KEY='python-dotenv-key'"
      ].join("\n")
    );

    expect(resolveVWorldApiKey({}, uiDir)).toBe("python-dotenv-key");
  });

  it("UI .env.local의 VWorld API 키를 읽는다", () => {
    const root = mkdtempSync(join(tmpdir(), "kraddr-geo-ui-runtime-"));
    tempDirs.push(root);
    const uiDir = join(root, "kraddr-geo-ui");
    mkdirSync(uiDir);
    writeFileSync(
      join(uiDir, ".env.local"),
      [
        "KRADDR_GEO_API_INTERNAL_URL=http://localhost:12201",
        "NEXT_PUBLIC_VWORLD_API_KEY=ui-dotenv-local-key"
      ].join("\n")
    );

    expect(resolveVWorldApiKey({}, uiDir)).toBe("ui-dotenv-local-key");
  });

  it("dotenv 값의 주석과 따옴표를 처리한다", () => {
    expect(parseDotenvValue('KRADDR_GEO_VWORLD_API_KEY="quoted-key"', "KRADDR_GEO_VWORLD_API_KEY")).toBe(
      "quoted-key"
    );
    expect(parseDotenvValue("# KRADDR_GEO_VWORLD_API_KEY=old", "KRADDR_GEO_VWORLD_API_KEY")).toBe("");
  });
});
