# CHANGELOG

본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따른다. 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따른다.

## [Unreleased]

### Changed
- **(BREAKING)** `kraddr.geo` 패키지의 저장 엔진을 SQLite + SpatiaLite에서 PostgreSQL + PostGIS로 전환한다. 패키지 이름은 그대로지만 내부 구현은 완전히 새로 작성한다. 이전 구현은 `v1` 브랜치에 보존되어 있다.
- GitHub 저장소 이름을 `python-kraddr-geo`로 명시하고, CLI 명령은 `kraddr-geo`, 환경변수 prefix는 `KRADDR_GEO_`, PostgreSQL DB 이름은 `kraddr_geo`로 통일한다.
- 개발 정책: PC 개발은 WSL의 ext4 위에서 진행하고 작업 완료 시 NTFS의 프로젝트 디렉토리로 카피한다. 데이터(`data/`)는 NTFS 프로젝트 디렉토리 아래에 두고 테스트도 이를 참조한다.
- **(BREAKING)** 라이브러리 진입점을 동기 `SpatialiteAddressStore`에서 비동기 `AsyncAddressClient`로 교체한다. 동기 호출이 필요하면 호출자가 `asyncio.run`으로 감싼다.
- 응답 구조를 vworld와 호환되도록 정렬하고 자체 필드는 `x_extension` 네임스페이스로 격리한다.
- 디버그/관리 UI를 monorepo 내부의 `debug-ui/` 대신 별도 Node.js 패키지 `kraddr-geo-ui`(Next.js 14 + shadcn/ui + react-kakao-maps-sdk)로 분리한다.
- 디버그/관리 UI는 내부망 전용으로 운영하며 애플리케이션 인증을 두지 않는다(ADR-013).

### Added
- 문서 구조에 `SKILL.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`를 도입한다.
- 외부 REST API(vworld, juso, epost, kakao maps)의 발급 절차와 호출 정책을 `docs/external-apis.md`로 정리한다.
- 시도별 ZIP 업로드와 작업 큐 기반 직렬 적재 워크플로(`/v1/admin/upload/sido-zip`, `/v1/admin/load/sido-batch`)를 사양으로 명시한다.
- `pyproject.toml`, `.env.example`, `Settings`, 기본 패키지 스캐폴드, 공통/주소 DTO와 단위 테스트를 추가한다.

### Removed
- 동기 라이브러리 API, monorepo 내부 디버그 UI, `ogr2ogr` subprocess 호출 경로를 사양에서 제거한다.

## 사양 기준일
2026-05-22
