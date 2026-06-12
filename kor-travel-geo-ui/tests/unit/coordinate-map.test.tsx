import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoordinateMap } from "@/components/vworld/CoordinateMap";
import { CoordinateMapSkeleton } from "@/components/vworld/LazyCoordinateMap";

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
