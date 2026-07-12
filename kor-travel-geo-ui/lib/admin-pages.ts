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

/** 사이드바 그룹 구성 (관리 홈은 그룹 위에 단독 노출). */
export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  { title: "데이터 관리", keys: ["sourceFiles", "files", "consistency"] },
  { title: "백업·운영", keys: ["backups", "dagster", "ops", "logs"] },
  { title: "시스템", keys: ["tables", "cache"] },
  { title: "설정", keys: ["settings"] }
];
