const SIDO_ALIASES: Record<string, string> = {
  서울: "seoul",
  부산: "busan",
  대구: "daegu",
  인천: "incheon",
  광주: "gwangju",
  대전: "daejeon",
  울산: "ulsan",
  세종: "sejong",
  경기: "gyunggi",
  강원: "gangwon",
  충북: "chungbuk",
  충남: "chungnam",
  전북: "jeonbuk",
  전남: "jeonnam",
  경북: "gyeongbuk",
  경남: "gyeongnam",
  제주: "jeju"
};

export function guessSido(filename: string): string | null {
  const lowered = filename.toLowerCase();
  for (const [korean, code] of Object.entries(SIDO_ALIASES)) {
    if (filename.includes(korean) || lowered.includes(code)) {
      return code;
    }
  }
  return null;
}
