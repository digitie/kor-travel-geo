/**
 * Admin 페이지 계약 상수 — 경로/제목(h1·네비 라벨)/짧은 설명의 단일 소스.
 * AppShell 네비, 각 page.tsx, 관리 홈 대시보드, Playwright spec이 함께 소비한다.
 * (아이콘은 React 의존을 피하기 위해 여기 두지 않는다 — AppShell에서 매핑)
 */

export type AdminPageKey =
  | "home"
  | "sourceFiles"
  | "files"
  | "consistency"
  | "backups"
  | "dagster"
  | "ops"
  | "logs"
  | "tables"
  | "cache"
  | "settings"
  | "load";

export interface AdminPageMeta {
  key: AdminPageKey;
  path: string;
  /** h1이자 사이드바 라벨. */
  title: string;
  /** PageHeader 부제 (간결한 한 줄, 없으면 미표시). */
  description?: string;
}

export const ADMIN_PAGES: Record<AdminPageKey, AdminPageMeta> = {
  home: {
    key: "home",
    path: "/admin",
    title: "관리 홈",
    description: "운영 상태 요약과 관리 기능 안내"
  },
  sourceFiles: {
    key: "sourceFiles",
    path: "/admin/source-files",
    title: "원천 파일",
    description: "주소 원천 파일 업로드부터 DB 반영까지"
  },
  files: {
    key: "files",
    path: "/admin/files",
    title: "파일 관리",
    description: "저장된 모든 파일의 연결·사용 현황 추적"
  },
  consistency: {
    key: "consistency",
    path: "/admin/consistency",
    title: "정합성 검증",
    description: "적재 데이터 검증 결과 확인과 수동 판정"
  },
  backups: {
    key: "backups",
    path: "/admin/backups",
    title: "백업/복원",
    description: "DB 백업 생성 · 복원 · 운영 교체(Hot-swap)"
  },
  dagster: {
    key: "dagster",
    path: "/admin/dagster",
    title: "Dagster",
    description: "오케스트레이션 run · schedule · sensor 관측"
  },
  ops: {
    key: "ops",
    path: "/admin/ops",
    title: "운영 이력",
    description: "릴리스 · 스냅샷 · 감사 이력과 성능 요약"
  },
  logs: {
    key: "logs",
    path: "/admin/logs",
    title: "로그",
    description: "최근 서버 로그 확인"
  },
  tables: {
    key: "tables",
    path: "/admin/tables",
    title: "테이블 통계",
    description: "PostgreSQL 테이블 행 수와 용량"
  },
  cache: {
    key: "cache",
    path: "/admin/cache",
    title: "캐시",
    description: "외부 API 캐시 상태"
  },
  settings: {
    key: "settings",
    path: "/admin/settings",
    title: "설정",
    description: "지도 키 · 공개 API 키 · 저장소 설정"
  },
  // 레거시 스텁 — 네비에는 노출하지 않고 라우트만 유지한다.
  load: {
    key: "load",
    path: "/admin/load",
    title: "적재",
    description: "적재 관련 화면 안내"
  }
};

export interface AdminNavGroup {
  title: string;
  keys: AdminPageKey[];
}

/** 최신 map admin의 작업 중심 IA를 geo 도메인에 맞춰 적용한다(관리 홈은 개요에 단독 노출). */
export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  { title: "데이터 관리", keys: ["sourceFiles", "files", "consistency"] },
  { title: "수집 파이프라인", keys: ["dagster", "ops"] },
  { title: "모니터링", keys: ["logs", "tables", "cache"] },
  { title: "시스템", keys: ["backups", "settings"] }
];

/** 관리자 셸 상단 바의 영역 이름. 제목은 "지오 - 페이지" 한 줄이다(@kor-travel/ui AdminShell). */
export const GEO_ADMIN_AREA = "지오";

/**
 * 상단 바 h1과 document.title의 문자열. `@kor-travel/ui`의 `formatAdminTitle(GEO_ADMIN_AREA, title)`과
 * 같은 결과다(tests/unit/admin-pages.test.ts가 대조한다). Playwright 스펙이 React 없이 import할 수 있게
 * 여기서는 순수 함수로 둔다.
 */
export function adminPageHeading(title: string): string {
  return `${GEO_ADMIN_AREA} - ${title}`;
}

export interface DebugPageMeta {
  path: string;
  title: string;
  description: string;
}

/** 조회·진단 화면의 경로/제목/설명 단일 소스(네비 라벨·상단 바·page.tsx가 함께 쓴다). */
export const DEBUG_PAGES = {
  geocode: { path: "/debug/geocode", title: "Geocode", description: "주소 좌표와 POI 반경 행정구역 확인" },
  reverse: { path: "/debug/reverse", title: "Reverse", description: "좌표 주변의 도로명·지번 후보 확인" },
  normalize: { path: "/debug/normalize", title: "Normalize", description: "주소 문자열의 행정구역·도로명 토큰 확인" },
  explain: { path: "/debug/explain", title: "Explain", description: "운영 엔진과 같은 search_path에서 실행 계획 확인" }
} as const satisfies Record<string, DebugPageMeta>;

/** 현재 경로의 페이지 제목·설명(가장 긴 경로 일치). 서버 렌더 첫 화면의 상단 바 제목에 쓴다. */
export function pageMetaForPath(pathname: string): { title: string; description?: string } | undefined {
  const candidates: Array<{ path: string; title: string; description?: string }> = [
    ...Object.values(ADMIN_PAGES),
    ...Object.values(DEBUG_PAGES)
  ];
  let best: { path: string; title: string; description?: string } | undefined;
  for (const page of candidates) {
    const matches =
      page.path === ADMIN_PAGES.home.path
        ? pathname === page.path
        : pathname === page.path || pathname.startsWith(`${page.path}/`);
    if (matches && (!best || page.path.length > best.path.length)) best = page;
  }
  return best ? { title: best.title, description: best.description } : undefined;
}
