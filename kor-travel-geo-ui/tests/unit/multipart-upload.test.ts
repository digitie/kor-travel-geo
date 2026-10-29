import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadSlotFile } from "@/lib/multipart-upload";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postJson: vi.fn(async () => ({ multipart_upload_id: "upload-test" }))
}));

const MIB = 1024 * 1024;

afterEach(() => vi.unstubAllGlobals());

function installTransport(truncate = false) {
  const sizes: number[] = [];
  let active = 0;
  let peak = 0;
  let completed = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    if (init.method === "PUT") {
      const size = (init.body as Blob).size;
      sizes.push(size);
      active += 1;
      peak = Math.max(peak, active);
      await Promise.resolve();
      active -= 1;
      const number = Number(new URL(url, "http://localhost").pathname.split("/").at(-1));
      return Response.json({
        part_number: number, part_etag: `part-${number}`,
        received_bytes: truncate ? size - 1 : size
      });
    }
    completed = true;
    return Response.json({ state: "awaiting_registration" });
  }));
  return { sizes, peak: () => peak, completed: () => completed };
}

describe("실제 전송 크기를 보존하는 multipart 업로드", () => {
  it("Next.js 기본 본문 한도 아래의 파트로 원본 전체를 보낸다", async () => {
    const transport = installTransport();
    await uploadSlotFile({
      sessionId: "session", slotId: "archive",
      file: new File([new Uint8Array(20 * MIB)], "source.zip"), partSizeBytes: 64 * MIB
    });
    expect(transport.sizes).toEqual([8 * MIB, 8 * MIB, 4 * MIB]);
    expect(transport.completed()).toBe(true);
  });

  it("큰 파일의 파트를 하나씩 보내 메모리 사용을 제한한다", async () => {
    const transport = installTransport();
    await uploadSlotFile({
      sessionId: "session", slotId: "archive",
      file: new File([new Uint8Array(20 * MIB)], "source.zip"), partSizeBytes: 8 * MIB
    });
    expect(transport.peak()).toBe(1);
  });

  it("서버 수신 크기가 다르면 완료 처리 전에 실패한다", async () => {
    const transport = installTransport(true);
    await expect(uploadSlotFile({
      sessionId: "session", slotId: "archive",
      file: new File(["archive"], "source.zip"), partSizeBytes: 8 * MIB
    })).rejects.toThrow("수신 크기");
    expect(transport.completed()).toBe(false);
  });
});
