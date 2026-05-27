import { describe, expect, it } from "vitest";
import {
  backupDownloadHref,
  backupProfileLabel,
  shaPrefix,
  stagePhase,
  terminalJobState
} from "@/lib/backup-workflow";

describe("backup-workflow", () => {
  it("proxy download URL을 API base와 v1 path로 정규화한다", () => {
    expect(backupDownloadHref("/v1/admin/backups/a/download?token=x")).toBe(
      "/api/proxy/v1/admin/backups/a/download?token=x"
    );
    expect(backupDownloadHref("/admin/backups/a/download?token=x")).toBe(
      "/api/proxy/v1/admin/backups/a/download?token=x"
    );
    expect(backupDownloadHref("https://example.test/a.tar.zst")).toBe(
      "https://example.test/a.tar.zst"
    );
  });

  it("작업 phase와 terminal 상태를 안정적으로 계산한다", () => {
    expect(stagePhase("pg_restore: table data")).toBe("restore");
    expect(stagePhase("checksum")).toBe("checksum");
    expect(stagePhase(null)).toBe("unknown");
    expect(terminalJobState("done")).toBe(true);
    expect(terminalJobState("running")).toBe(false);
  });

  it("checksum과 profile 표시값을 축약한다", () => {
    expect(shaPrefix("abcdef0123456789")).toBe("abcdef012345");
    expect(shaPrefix(null)).toBe("-");
    expect(backupProfileLabel("forensic")).toBe("forensic");
    expect(backupProfileLabel("custom")).toBe("-");
  });
});
