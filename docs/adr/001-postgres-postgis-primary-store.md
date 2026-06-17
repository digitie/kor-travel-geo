# ADR-001: PostgreSQL + PostGIS를 1차 저장소로 채택한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

## 컨텍스트
이전(v1) 구현은 SQLite + SpatiaLite를 사용했다. 확장 로드 가능 여부가 실행 환경마다 달랐고, 대량 적재(전국 11개 마스터 + 도형) 시 쿼리 성능과 동시성 제어가 부족했다. EXPLAIN 결과의 재현성도 떨어졌다.

## 결정
PostgreSQL 16 + PostGIS 3.4를 1차 저장소로 채택한다. SpatiaLite 기반 구현은 `v1` 브랜치에 보존하고 `main`에서는 더 이상 유지보수하지 않는다.

## 근거
- 도로명주소 전자지도(SHP) 적재에 GDAL Python binding이 안정적으로 동작
- `pg_trgm`, `unaccent`, MV(머티리얼라이즈드 뷰), 윈도우 함수 등 쿼리 도구 풍부
- `psycopg` async 드라이버로 SQLAlchemy 2 async 패턴과 자연스럽게 결합
- 디버거 EXPLAIN과 운영 쿼리가 같은 환경에서 평가됨

## 결과(긍정)
- 쿼리 튜닝의 자유도(인덱스 hint, `SET LOCAL`, 파티셔닝 등)
- 운영 표준 도구(pg_dump, repmgr 등) 활용 가능

## 결과(부정)
- 배포 의존성 증가(PostgreSQL 서버 운영)
- 단일 파일 배포(SpatiaLite의 장점)가 사라짐

## 후속
- (open) ARM 8GB 환경에서 `pg_pool_size`, `statement_timeout`, `work_mem`의 권장값 실측
