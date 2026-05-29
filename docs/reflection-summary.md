# 사양 첨부파일 반영 요약

## 입력

2026-05-22 사용자가 두 개의 docx 사양서를 master 브랜치 문서에 반영하도록 지시했다.

- `한국 주소 라이브러리 — 프론트엔드 + AI 협업 가이드 (Part A + Part B)`
- `한국 주소 라이브러리 백엔드 패키지 사양서 (Python Library API + REST API + File Loaders)`

지시 조건:

> 충돌나는 부분은 첨부파일이 우선하고, 반영 내용 요약한 md 파일도 만들어.

## 충돌 정책 적용 결과

기존 SpatiaLite + SQLite 기반 문서와 첨부 사양(PostgreSQL + PostGIS 기반)이 거의 모든 영역에서 충돌한다. 첨부파일을 우선해 master 문서를 새 사양으로 재구성했다.

| 영역 | 이전 (v1) | 신규 (master, 첨부 사양 + 사용자 추가 명시) |
|------|-----------|---------------------------------------------|
| GitHub 저장소 이름 | `python-kraddr-geo` | 동일 (`python-kraddr-geo`) |
| Python 패키지 | `kraddr.geo` | 동일 (`kraddr.geo`) |
| 백엔드 CLI / env / DB | `kraddr.geo` 라이브러리 직접 사용 | CLI `kraddr-geo`, env `KRADDR_GEO_*`, DB `kraddr_geo` |
| 프론트엔드 | monorepo `debug-ui/` | 별도 Node.js 패키지 `kraddr-geo-ui` |
| 저장소 | SQLite + SpatiaLite | PostgreSQL 16 + PostGIS 3.4 |
| 라이브러리 진입점 | 동기 `SpatialiteAddressStore` (+ async 보조) | async-only `AsyncAddressClient` (ADR-002) |
| 응답 구조 | 자체 DTO | vworld 호환 + `x_extension` (ADR-003) |
| ORM | SQLAlchemy + 일반 model | SQLAlchemy 2 async + raw SQL repository (ADR-004) |
| 로더 | `ogr2ogr` subprocess | GDAL Python binding(in-process), CP949 명시, 진행률 callback (ADR-005) |
| 증분 적재 | 매니페스트 부분 지원 | `MVM_RES_CD` 기반 INSERT/UPDATE/DELETE 머지 |
| UI | monorepo `debug-ui/` (FastAPI + Next.js) | 별도 Node.js 패키지 `kraddr-geo-ui` (Next.js 16 + Tailwind + MapLibre GL JS + VWorld WMTS) |
| UI 인증 | 단순 노출 | 내부망 전용, 애플리케이션 인증 없음 (ADR-013) |
| 적재 워크플로 | 단일 폼 | 2단계(업로드 완료 → 일괄 처리), `Semaphore(1)` 직렬 큐 (ADR-006) |

## 추가/갱신/유지된 파일

### 신규 추가 (12개)

| 파일 | 출처 |
|------|------|
| `SKILL.md` | 첨부 §B3 — 에이전트 작업 매뉴얼 |
| `CHANGELOG.md` | 첨부 §B2 — 릴리즈 노트 placeholder |
| `docs/architecture.md` | 첨부 백엔드 §1·§7·§8 + 프론트 §A1 |
| `docs/decisions.md` | 첨부 §B2.3 — ADR-001~006, 013 초기 등록 |
| `docs/data-model.md` | 첨부 백엔드 §4·§7·§9.3 + §3 부록 — DDL/MV/MVM 매핑 |
| `docs/tasks.md` | 첨부 §B2.6 — T-001~025 초기 백로그 |
| `docs/resume.md` | 첨부 §B2.4 — 현재 진척도 + 다음 한 작업(T-001) |
| `docs/journal.md` | 첨부 §B2.5 — 첫 두 엔트리 |
| `docs/backend-package.md` | 첨부 백엔드 사양서 전체 정리본 |
| `docs/frontend-package.md` | 첨부 프론트 Part A 전체 정리본 |
| `docs/agent-guide.md` | 첨부 Part B 전체 정리본 |
| `docs/external-apis.md` | 첨부 §13.3 — vworld/juso/epost 발급·호출·정책 |

### 기존 파일 갱신 (7개)

| 파일 | 갱신 요지 |
|------|----------|
| `AGENTS.md` | 새 패키지/계층/DO NOT 룰 반영, 신규 문서로의 진입점 추가 |
| `README.md` | `kraddr-geo` 빠른 시작, 진입점, 디렉토리 한 줄 설명, ADR 요약, 문서 지도 |
| `docs/address-db-schema.md` | PostgreSQL + PostGIS 11개 마스터 + 보조 + MV 요약. 세부는 data-model로 위임 |
| `docs/code-guide-for-beginners.md` | 새 디렉토리(`dto/core/infra/client/api/cli`), 프론트엔드 별도 패키지, 작업 사이클 |
| `docs/geocoding-readiness.md` | PostgreSQL/PostGIS readiness 체크리스트, GDAL/CP949 함정, `kraddr-geo validate` |
| `docs/reverse-geocoding.md` | `AsyncAddressClient.reverse`, ReverseRepo Protocol, 출입구 hit + 동 polygon fallback, ZipSource 4단계 |
| `docs/spatialite-vworld-implementation.md` | 파일명만 유지, 내용은 PostgreSQL + PostGIS / vworld 호환 구현으로 전환 (ADR-001 참조) |

### 신규 요약 (1개)

| 파일 | 역할 |
|------|------|
| `docs/reflection-summary.md` | 본 문서 — 사양 첨부파일 반영 결과 요약 |

## 사용자 추가 명시 (이후 반영)

다음 항목은 첨부 사양서에 없었지만 별도 지시로 master에 명시되었다:

- **개발 환경**: PC 개발은 WSL의 ext4 위에서 진행하고 작업 완료 시 NTFS의 프로젝트 디렉토리로 카피한다. `AGENTS.md`, `SKILL.md`, `docs/architecture.md`에 정책 섹션이 들어간다.
- **데이터 위치**: 도로명주소 ZIP/SHP, postal TXT 등은 NTFS의 프로젝트 디렉토리 `data/` 아래에 둔다. ext4 작업 디렉토리에는 심볼릭 링크 또는 절대경로로 참조한다. 테스트도 NTFS 측 `data/`를 reference로 삼는다.
- **식별자 통일**: GitHub 저장소 = `python-kraddr-geo`, Python import = `kraddr.geo`, CLI = `kraddr-geo`, env prefix = `KRADDR_GEO_`, PostgreSQL DB = `kraddr_geo`, 프론트엔드 패키지 = `kraddr-geo-ui`. `AGENTS.md`/`SKILL.md`의 식별자 표에 기록되어 혼동을 막는다.

## 첨부 사양에서 다루지 않은 항목 (master에 남긴 결정)

- 파일명 컨벤션: 첨부는 대문자 `ARCHITECTURE.md` 등을 권했으나, 기존 docs/ 컨벤션(영어 소문자 kebab)을 유지해 충돌을 줄였다. 단 루트 `SKILL.md`, `CHANGELOG.md`, `AGENTS.md`, `README.md`는 대문자 컨벤션 그대로.
- `docs/spatialite-vworld-implementation.md` 파일명은 의미상 부정확하지만 보존 — 첫 단락에 명시적으로 PostgreSQL + PostGIS 전환을 알린다.
- 외부 API 폴백의 구체 알고리즘(예: vworld → juso 순서)은 `docs/spatialite-vworld-implementation.md`와 `docs/backend-package.md`에 다중 인용으로 보존했다.
- 첨부 사양서 본문에 등장한 코드 예시(파이썬/타입스크립트)는 가독성을 위해 핵심만 옮기고, 긴 reducer/페이지 컴포넌트 같은 부분은 §A6.3.4 등 절 번호로 인용했다.

## 다음 단계

1. `docs/resume.md`의 "다음 한 작업"(T-001 `pyproject.toml` 작성)부터 시작.
2. 사양과 다른 결정이 생기면 `docs/decisions.md`에 새 ADR 추가.
3. 코드를 작성하기 시작하면 `docs/journal.md`를 PR마다 갱신.

## 추적용 메타

- 사양 기준일: 2026-05-22 (첨부 두 파일 모두)
- 반영 브랜치: `claude/move-progress-to-v1-t9qM4` → master로 머지될 변경 후보
- 이전 코드 보존: `v1` 브랜치
