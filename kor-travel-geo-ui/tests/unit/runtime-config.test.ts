import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { parseDotenvValue, resolveDagsterPublicUrl, resolveVWorldApiKey } from "@/lib/runtime-config";

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
        KTG_VWORLD_API_KEY: "python-key",
        NEXT_PUBLIC_VWORLD_API_KEY: "ui-key"
      })
    ).toBe("python-key");
  });

  it("Python API 키가 없으면 UI 전용 환경변수를 사용한다", () => {
    const root = mkdtempSync(join(tmpdir(), "kor-travel-geo-ui-runtime-"));
    tempDirs.push(root);

    expect(resolveVWorldApiKey({ NEXT_PUBLIC_VWORLD_API_KEY: "ui-key" }, root)).toBe(
      "ui-key"
    );
  });

  it("Python 프로젝트 루트 .env의 VWorld API 키를 읽는다", () => {
    const root = mkdtempSync(join(tmpdir(), "kor-travel-geo-ui-runtime-"));
    tempDirs.push(root);
    const uiDir = join(root, "kor-travel-geo-ui");
    mkdirSync(uiDir);
    writeFileSync(
      join(root, ".env"),
      [
        "# local secrets",
        "KTG_JUSO_API_KEY=unused",
        "KTG_VWORLD_API_KEY='python-dotenv-key'"
      ].join("\n")
    );

    expect(resolveVWorldApiKey({}, uiDir)).toBe("python-dotenv-key");
  });

  it("UI .env.local의 VWorld API 키를 읽는다", () => {
    const root = mkdtempSync(join(tmpdir(), "kor-travel-geo-ui-runtime-"));
    tempDirs.push(root);
    const uiDir = join(root, "kor-travel-geo-ui");
    mkdirSync(uiDir);
    writeFileSync(
      join(uiDir, ".env.local"),
      [
        "KTG_API_INTERNAL_URL=http://localhost:12501",
        "NEXT_PUBLIC_VWORLD_API_KEY=ui-dotenv-local-key"
      ].join("\n")
    );

    expect(resolveVWorldApiKey({}, uiDir)).toBe("ui-dotenv-local-key");
  });

  it("dotenv 값의 주석과 따옴표를 처리한다", () => {
    expect(parseDotenvValue('KTG_VWORLD_API_KEY="quoted-key"', "KTG_VWORLD_API_KEY")).toBe(
      "quoted-key"
    );
    expect(parseDotenvValue("# KTG_VWORLD_API_KEY=old", "KTG_VWORLD_API_KEY")).toBe("");
  });

  describe("resolveDagsterPublicUrl", () => {
    it("공개 URL(KTG_DAGSTER_PUBLIC_URL)이 내부 URL보다 우선한다", () => {
      expect(
        resolveDagsterPublicUrl({
          KTG_DAGSTER_PUBLIC_URL: "https://geo-dagster.example.com/",
          KTG_DAGSTER_URL: "http://127.0.0.1:12502"
        })
      ).toBe("https://geo-dagster.example.com/");
    });

    it("공개 URL이 없으면 내부 KTG_DAGSTER_URL로 폴백한다 (dev 기본값 동등성)", () => {
      const root = mkdtempSync(join(tmpdir(), "kor-travel-geo-ui-runtime-"));
      tempDirs.push(root);

      expect(resolveDagsterPublicUrl({ KTG_DAGSTER_URL: "http://127.0.0.1:19999" }, root)).toBe(
        "http://127.0.0.1:19999"
      );
    });

    it("아무 것도 설정되지 않으면 backend Settings.dagster_url 기본값으로 폴백한다", () => {
      const root = mkdtempSync(join(tmpdir(), "kor-travel-geo-ui-runtime-"));
      tempDirs.push(root);
      const uiDir = join(root, "kor-travel-geo-ui");
      mkdirSync(uiDir);

      expect(resolveDagsterPublicUrl({}, uiDir)).toBe("http://127.0.0.1:12502");
    });
  });
});
