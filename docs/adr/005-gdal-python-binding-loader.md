# ADR-005: 로더는 `ogr2ogr` subprocess 대신 GDAL Python binding을 쓴다

- 상태: **partially superseded by ADR-012** (텍스트 정본 1차로 전환, GDAL은 polygon/폴리라인 적재에만 사용)
- 날짜: 2026-05-22
- 결정자: human

## 컨텍스트
이전 구현은 `ogr2ogr` subprocess를 사용했다. stderr 파싱, 진행률 미보고, 환경변수 누수 등 비용이 컸다.

## 결정
`osgeo.gdal.VectorTranslate`를 in-process로 호출한다. CP949 디코딩은 `open_options=["ENCODING=CP949"]`로 명시. `PG_USE_COPY`는 `gdal.config_options` 컨텍스트 매니저로 한정 적용(`gdal.SetConfigOption` 전역 호출 금지).

## 근거
- 진행률 callback으로 0~1.0 보고 — 작업 큐와 UI 프로그래스바 연결
- callback 안의 `cancel_event` 확인으로 협조적 취소
- subprocess 의존, stderr 파싱 비용 제거

## 결과(긍정)
- 작업 상태 관찰이 깔끔. 취소 동작 신뢰성 ↑
- 환경변수 누수 위험 사라짐

## 결과(부정)
- GDAL Python binding 의존성 추가(설치 환경 까다로움) — Docker 이미지로 표준화
