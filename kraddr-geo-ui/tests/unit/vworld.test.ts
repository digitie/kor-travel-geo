import { describe, expect, it } from "vitest";
import { getVWorldMaxZoom, getVWorldRasterStyle, getVWorldTileUrl } from "@/lib/vworld";

describe("VWorld MapLibre style", () => {
  it("VWorld WMTS URL은 좌표 타일 placeholder와 API key를 보존한다", () => {
    expect(getVWorldTileUrl("sample-key", "Base")).toBe(
      "https://api.vworld.kr/req/wmts/1.0.0/sample-key/Base/{z}/{y}/{x}.png"
    );
  });

  it("항공사진 레이어는 jpeg 타일을 사용한다", () => {
    expect(getVWorldTileUrl("sample-key", "Satellite")).toMatch(/Satellite\/\{z\}\/\{y\}\/\{x\}\.jpeg$/);
  });

  it("MapLibre raster style은 VWorld 타일 source와 layer를 연결한다", () => {
    const style = getVWorldRasterStyle("sample-key", "gray");

    expect(style.sources.vworld).toMatchObject({
      attribution: "공간정보 오픈플랫폼 브이월드",
      maxzoom: 19,
      tileSize: 256,
      type: "raster"
    });
    expect(style.layers).toEqual([
      {
        id: "vworld",
        source: "vworld",
        type: "raster"
      }
    ]);
  });

  it("항공사진 계열은 VWorld z18 한계에 맞춘다", () => {
    expect(getVWorldMaxZoom("Base")).toBe(19);
    expect(getVWorldMaxZoom("Satellite")).toBe(18);
    expect(getVWorldRasterStyle("sample-key", "Hybrid").sources.vworld).toMatchObject({
      maxzoom: 18
    });
  });
});
