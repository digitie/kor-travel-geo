# ADR-018: PostGIS 보조 extension은 `x_extension` 스키마에 격리한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #10 review 반영

## 컨텍스트

PostGIS, `pg_trgm`, `unaccent`는 운영 DB에 반드시 필요한 extension이지만, 마스터 테이블과 같은 `public` 스키마에 섞어 두면 다음 문제가 생긴다.

1. DDL 리뷰에서 extension 객체와 서비스 테이블이 섞여 스키마 책임이 흐려진다.
2. 실수로 `DROP SCHEMA public CASCADE` 또는 테스트 초기화 스크립트가 extension 객체까지 건드릴 수 있다.
3. 권한 분리, 백업/복구, diff 리뷰에서 "서비스 데이터"와 "DB 기능 제공 객체"를 구분하기 어렵다.

## 결정

extension은 전용 스키마 `x_extension`에 설치한다.

```sql
CREATE SCHEMA IF NOT EXISTS x_extension;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA x_extension;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA x_extension;
SET search_path = public, x_extension;
```

애플리케이션 연결은 `options=-csearch_path=public,x_extension`를 사용한다. Alembic, raw SQL repository, loader, CLI 모두 같은 search path를 전제로 한다.

## 근거

- `public`은 서비스 테이블·MV·인덱스의 기본 스키마로 유지하고, extension 제공 함수/타입은 별도 영역에 둔다.
- PostGIS 함수(`ST_DWithin`, `ST_Transform` 등)를 SQL에서 schema prefix 없이 쓸 수 있으면서도 객체 소유권은 분리된다.
- 리뷰어가 DDL을 볼 때 extension 설치 위치를 명확히 확인할 수 있다.

## 결과(긍정)

- extension과 서비스 DDL의 책임 경계가 선명하다.
- 테스트 DB 재생성·운영 DB 권한 점검 시 extension 영역을 별도로 확인할 수 있다.
- 누군가 `CREATE EXTENSION ... WITH SCHEMA public`으로 되돌리는 변경을 ADR 위반으로 리뷰할 수 있다.

## 결과(부정)

- 모든 연결 경로가 `search_path=public,x_extension`를 지켜야 한다. 누락되면 PostGIS 함수 탐색 오류가 날 수 있다.
- 운영 DB에 이미 `public` 스키마로 설치된 extension이 있다면 초기 마이그레이션 전에 정리 절차가 필요하다.
