import { describe, expect, it } from "vitest";
import {
  getVWorldMaxZoom,
  getVWorldRasterStyle,
  getVWorldTileUrl,
  isVWorldTileError,
  redactVWorldTileUrl
} from "@/lib/vworld";

describe("VWorld MapLibre style", () => {
  it("VWorld WMTS URL은 좌표 타일 placeholder와 API key를 보존한다", () => {
    expect(getVWorldTileUrl("sample-key", "Base")).toBe(
      "https://api.vworld.kr/req/wmts/1.0.0/sample-key/Base/{z}/{y}/{x}.png"
    );
  });

  it("gray 레이어는 VWorld WMTS white 레이어로 요청한다", () => {
    expect(getVWorldTileUrl("sample-key", "gray")).toBe(
      "https://api.vworld.kr/req/wmts/1.0.0/sample-key/white/{z}/{y}/{x}.png"
    );
  });

  it("항공사진 레이어는 jpeg 타일을 사용한다", () => {
    expect(getVWorldTileUrl("sample-key", "Satellite")).toMatch(/Satellite\/\{z\}\/\{y\}\/\{x\}\.jpeg$/);
  });

  it("MapLibre raster style은 VWorld 타일 source와 layer를 연결한다", () => {
    const style = getVWorldRasterStyle("sample-key", "gray");

    expect(style.sources["vworld-gray"]).toMatchObject({
      attribution: "공간정보 오픈플랫폼 브이월드",
      maxzoom: 19,
      tileSize: 256,
      type: "raster"
    });
    expect(style.layers).toEqual([
      {
        id: "vworld-gray-layer",
        minzoom: 0,
        source: "vworld-gray",
        type: "raster"
      }
    ]);
  });

  it("항공사진 계열은 VWorld z18 한계에 맞춘다", () => {
    expect(getVWorldMaxZoom("Base")).toBe(19);
    expect(getVWorldMaxZoom("Satellite")).toBe(18);
    expect(getVWorldRasterStyle("sample-key", "Hybrid").sources["vworld-Hybrid"]).toMatchObject({
      maxzoom: 18
    });
  });

  it("Hybrid 레이어는 Satellite 배경 위에 Hybrid 오버레이를 쌓는다", () => {
    const style = getVWorldRasterStyle("sample-key", "Hybrid");

    expect(Object.keys(style.sources)).toEqual(["vworld-satellite", "vworld-Hybrid"]);
    expect(style.layers).toEqual([
      {
        id: "vworld-satellite-layer",
        source: "vworld-satellite",
        type: "raster",
        minzoom: 0
      },
      {
        id: "vworld-Hybrid-layer",
        source: "vworld-Hybrid",
        type: "raster",
        minzoom: 0
      }
    ]);
  });

  it("VWorld tile 오류를 upstream helper로 분류한다", () => {
    expect(
      isVWorldTileError({
        error: Object.assign(new Error("not found"), {
          status: 404,
          url: "https://api.vworld.kr/req/wmts/1.0.0/sample-key/Base/1/2/3.png"
        }),
        sourceId: "vworld-Base"
      } as never)
    ).toBe(true);
  });

  it("VWorld tile URL의 API key를 upstream helper로 마스킹한다", () => {
    const redacted = redactVWorldTileUrl(
      "https://api.vworld.kr/req/wmts/1.0.0/sample-key/Base/1/2/3.png"
    );

    expect(redacted).toBe("https://api.vworld.kr/req/wmts/1.0.0/***/Base/1/2/3.png");
    expect(redacted).not.toContain("sample-key");
    expect(redacted.startsWith("https://api.vworld.kr/req/wmts/1.0.0/")).toBe(true);
    expect(redacted.endsWith("/Base/1/2/3.png")).toBe(true);
  });
});
