import { describe, expect, it } from "vitest";
import { guessSido } from "@/lib/sido";

describe("guessSido", () => {
  it("한글 시도명을 영문 코드로 매핑한다", () => {
    expect(guessSido("202604_서울특별시.zip")).toBe("seoul");
    expect(guessSido("강원특별자치도_51000.zip")).toBe("gangwon");
  });

  it("파일명의 영문 코드도 인식한다", () => {
    expect(guessSido("rnaddrkor_gyeongbuk.txt")).toBe("gyeongbuk");
    expect(guessSido("unknown.zip")).toBeNull();
  });
});
