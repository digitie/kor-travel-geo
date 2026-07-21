import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CandidateAddressSummary } from "@/components/debug/CandidateAddressSummary";

describe("CandidateAddressSummary", () => {
  it("후보가 없으면 아무 것도 렌더링하지 않는다", () => {
    const { container } = render(<CandidateAddressSummary candidates={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("주소가 없는 후보(sppn/region 등)는 건너뛴다", () => {
    const { container } = render(<CandidateAddressSummary candidates={[{ address: null }, {}]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("도로명 주소 후보를 '도로명' 라벨로 표시한다", () => {
    render(
      <CandidateAddressSummary
        candidates={[
          {
            address: {
              type: "road",
              road_address: "서울특별시 강남구 테헤란로 152",
              parcel_address: null,
              full: "서울특별시 강남구 테헤란로 152"
            }
          }
        ]}
      />
    );

    expect(screen.getByText("도로명")).toBeInTheDocument();
    expect(screen.getByText("서울특별시 강남구 테헤란로 152")).toBeInTheDocument();
  });

  it("역지오코딩 road+parcel 후보 쌍을 모두 표시한다 (같은 건물이어도 드롭되지 않음)", () => {
    render(
      <CandidateAddressSummary
        candidates={[
          {
            address: {
              type: "road",
              road_address: "서울특별시 동대문구 왕산로 189-4",
              parcel_address: null,
              full: "서울특별시 동대문구 왕산로 189-4"
            }
          },
          {
            address: {
              type: "parcel",
              road_address: null,
              parcel_address: "서울특별시 동대문구 청량리동 819-1",
              full: "서울특별시 동대문구 청량리동 819-1"
            }
          }
        ]}
      />
    );

    expect(screen.getByText("도로명")).toBeInTheDocument();
    expect(screen.getByText("지번")).toBeInTheDocument();
    expect(screen.getByText("서울특별시 동대문구 왕산로 189-4")).toBeInTheDocument();
    expect(screen.getByText("서울특별시 동대문구 청량리동 819-1")).toBeInTheDocument();
  });

  it("road_address/parcel_address가 없으면 full로 폴백한다", () => {
    render(
      <CandidateAddressSummary
        candidates={[{ address: { type: "road", full: "서울특별시 강남구 역삼동 819-1" } }]}
      />
    );

    expect(screen.getByText("서울특별시 강남구 역삼동 819-1")).toBeInTheDocument();
  });
});
