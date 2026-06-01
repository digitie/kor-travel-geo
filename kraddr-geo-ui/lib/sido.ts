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

const REGEX_SPECIAL_CHARS = new Set(["\\", "^", "$", ".", "*", "+", "?", "(", ")", "[", "]", "{", "}", "|"]);
const SIDO_MATCHERS = Object.entries(SIDO_ALIASES).map(([korean, code]) => ({
  code,
  pattern: new RegExp(`${escapeRegExp(korean)}|${escapeRegExp(code)}`, "i")
}));

export function guessSido(filename: string): string | null {
  for (const matcher of SIDO_MATCHERS) {
    if (matcher.pattern.test(filename)) {
      return matcher.code;
    }
  }
  return null;
}

function escapeRegExp(value: string): string {
  let escaped = "";
  for (const char of value) {
    escaped += REGEX_SPECIAL_CHARS.has(char) ? "\\" + char : char;
  }
  return escaped;
}
