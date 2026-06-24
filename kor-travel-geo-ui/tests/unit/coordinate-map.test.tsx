import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoordinateMap } from "@/components/vworld/CoordinateMap";
import { CoordinateMapSkeleton } from "@/components/vworld/LazyCoordinateMap";
import { isMapUsable } from "@/components/vworld/map-utils";

vi.mock("maplibre-gl", () => ({
  default: {
    Map: vi.fn(),
    Marker: vi.fn(),
    NavigationControl: vi.fn()
  }
}));

const originalApiKey = process.env.NEXT_PUBLIC_VWORLD_API_KEY;

afterEach(() => {
  if (originalApiKey === undefined) {
    delete process.env.NEXT_PUBLIC_VWORLD_API_KEY;
    return;
  }

  process.env.NEXT_PUBLIC_VWORLD_API_KEY = originalApiKey;
});

describe("CoordinateMap", () => {
  it("VWorld API 키가 없으면 좌표 프리뷰 fallback을 렌더링한다", () => {
    delete process.env.NEXT_PUBLIC_VWORLD_API_KEY;

    render(<CoordinateMap point={null} />);

    expect(screen.getByText("좌표 대기")).toBeInTheDocument();
    expect(screen.getByText("VWorld API 키 미설정")).toBeInTheDocument();
  });

  it("동적 로딩 중 같은 크기의 skeleton을 렌더링한다", () => {
    render(<CoordinateMapSkeleton />);

    expect(screen.getByLabelText("VWorld 지도 로딩")).toBeInTheDocument();
    expect(screen.getByText("지도 로딩 중")).toBeInTheDocument();
  });
});

describe("isMapUsable (overlay teardown guard)", () => {
  type MapArg = Parameters<typeof isMapUsable>[0];
  const fakeMap = (props: Record<string, unknown>): MapArg => props as unknown as MapArg;

  it("_removed된 map이면 false — overlay cleanup이 getLayer 호출 전에 빠져 크래시를 막는다", () => {
    expect(isMapUsable(fakeMap({ _removed: true, style: undefined }))).toBe(false);
  });

  it("style이 사라진 map이면 false (setStyle(null) 진행 중 등)", () => {
    expect(isMapUsable(fakeMap({ _removed: false, style: undefined }))).toBe(false);
  });

  it("살아있는 map이면 true", () => {
    expect(isMapUsable(fakeMap({ _removed: false, style: {} }))).toBe(true);
  });
});
