# CHANGELOG

본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따른다. 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따른다.

## [Unreleased]

### Changed
- **(BREAKING)** 백엔드 저장소를 SQLite + SpatiaLite 기반 `kraddr.geo`에서 PostgreSQL + PostGIS 기반 `addr-kr`로 전환한다. 이전 구현은 `v1` 브랜치에 보존되어 있다.
- **(BREAKING)** 라이브러리 진입점을 동기 `SpatialiteAddressStore`에서 비동기 `AsyncAddressClient`로 교체한다. 동기 호출이 필요하면 호출자가 `asyncio.run`으로 감싼다.
- 응답 구조를 vworld와 호환되도록 정렬하고 자체 필드는 `x_extension` 네임스페이스로 격리한다.
- 디버그/관리 UI를 monorepo 내부의 `debug-ui/` 대신 별도 Node.js 패키지 `addr-kr-ui`(Next.js 14 + shadcn/ui + react-kakao-maps-sdk)로 분리한다.

### Added
- 문서 구조에 `SKILL.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`를 도입한다.
- 외부 REST API(vworld, juso, epost, kakao maps)의 발급 절차와 호출 정책을 `docs/external-apis.md`로 정리한다.
- 시도별 ZIP 업로드와 작업 큐 기반 직렬 적재 워크플로(`/v1/admin/upload/sido-zip`, `/v1/admin/load/sido-batch`)를 사양으로 명시한다.

### Removed
- 동기 라이브러리 API, monorepo 내부 디버그 UI, `ogr2ogr` subprocess 호출 경로를 사양에서 제거한다.

## 사양 기준일
2026-05-22
