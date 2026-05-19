import { describe, expect, it } from "vitest";

import { mapBounds, toPercent } from "./kakao-map-panel";
import type { AddressPlace, Coordinate } from "@/data/address-data";

describe("KakaoMapPanel static preview helpers", () => {
  it("keeps the selected address at the static map center", () => {
    const selected = { lat: 37.46665558513095, lng: 129.14822031884484 };
    const bounds = mapBounds(
      [
        place("north-east", { lat: 37.46937048573197, lng: 129.15241316724595 }),
        place("selected", selected),
        place("west", { lat: 37.46692339497277, lng: 129.14540155151278 }),
      ],
      selected,
    );

    expect(toPercent(selected, bounds)).toEqual({ x: 50, y: 50 });
  });
});

function place(id: string, coordinate: Coordinate): AddressPlace {
  return {
    id,
    title: id,
    category: "road",
    roadAddress: id,
    jibunAddress: "",
    postalCode: "",
    legalDongCode: "",
    roadNameCode: "",
    pnu: "",
    coordinate,
    boundary: [],
    radiusMeters: 40,
    updatedAt: "",
    tags: [],
    boundaryName: "",
    boundaryLevel: "",
    coordinateSource: "test",
  };
}
