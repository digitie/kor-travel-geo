# 지오코딩 준비 상태

`addr-kr`이 정상 동작하려면 PostgreSQL + PostGIS 환경, 마스터 + 보조 테이블 적재, MV refresh, ANALYZE까지 끝난 상태가 필요하다. 본 문서는 그 체크리스트와 알려진 빈틈을 정리한다.

> 이전(v1) SpatiaLite 기반 readiness 기준은 `v1` 브랜치 문서에서 본다. master는 PostgreSQL + PostGIS 기준만 다룬다(ADR-001).

## 강한 입력 데이터

| 자료 | 역할 |
|------|------|
| 도로명주소 전자지도 (시도별 SHP) | 11개 마스터의 원천 — 출입구 좌표가 지오코딩 1차 데이터 |
| 기초구역 (`TL_KODIS_BAS`) | 우편번호 polygon. 역지오코딩의 zipcode lookup |
| 사서함 (`postal_pobox`) | 우편번호 4단계 우선순위의 한 축 |
| 다량배달처 (`postal_bulk_delivery`) | 같은 `bd_mgt_sn`에 별도 우편번호가 필요한 케이스 |
| 외부 API (vworld, juso) | 폴백 (`fallback="api"`) 및 자동 다운로드(epost) |

## 환경 readiness 체크리스트

1. **PostgreSQL 16 + PostGIS 3.4** 설치 및 기동
2. `pg_trgm`, `unaccent` 확장 설치
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS unaccent;
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
3. `Settings.pg_dsn` 설정 (`postgresql+psycopg://...`)
4. `alembic upgrade head`로 DDL 적용 (마스터 11개 + 보조 + 메타 + MV 정의)
5. 17개 시도 ZIP 적재 (`addr-kr load all-sidos /data/jusoMap/202605 --mode full`)
6. `addr-kr load pobox`, `addr-kr load bulk`로 보조 우편번호 적재
7. `addr-kr refresh mv` → `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`
8. `addr-kr refresh vacuum` → 통계 갱신 (`VACUUM (ANALYZE) tl_spbd_buld` 등)
9. `addr-kr validate all` — 행 수, FK, MV 일관성 검사

## 검증 시나리오

- 17개 시도 전체 적재 후 `tl_spbd_buld` row count 비교 (시도별 합과 일치하는지)
- `mv_geocode_target` 행 수 = 출입구 hit 가능 건물 수
- 도로명·지번 매칭 쿼리에 `EXPLAIN(ANALYZE)`로 인덱스 사용 확인
- 샘플 주소 100건에 대해 vworld 원응답과 `AsyncAddressClient.geocode` 결과 비교 (좌표 오차 < 10m 비율 측정)
- 역지오코딩: 임의 (lon, lat) 1,000건을 입력해 `/v1/address/reverse`가 출입구 hit / 동 폴리곤 fallback / NOT_FOUND 비율을 측정

## 알려진 빈틈

- **GDAL Python binding 환경 의존성**: 시도별 SHP 적재는 GDAL 3.8+ 필요. 운영은 Docker 이미지로 표준화 권장(ADR-005).
- **CP949 디코딩 누락 위험**: `gdal.OpenEx(..., open_options=["ENCODING=CP949"])`를 항상 명시. 누락 시 한글 깨짐 그대로 적재되는데 인덱스도 깨진 키로 만들어지므로 즉시 발견하기 어렵다.
- **`MVM_RES_CD` 코드 신규 도입**: 데이터셋이 시간 흐름에 따라 새 코드를 추가할 수 있다. 매핑은 `load_codes` 테이블 또는 settings에서 hot-fix 가능(SKILL.md §4-6).
- **외부 API 쿼터 침범**: vworld/juso 일 한도 도달 시 자동 fallback 비활성화 로직이 필요(`docs/external-apis.md` 호출 정책).
- **fuzzy 매칭 임계값**: `pg_trgm.similarity_threshold = 0.42`로 검증되어 있다. 0.3 미만은 noisy, 0.5 이상은 reject 과다. 데이터셋 갱신 시 재검증 권장.
- **좌표계 혼동**: 외부 인터페이스는 `(lon, lat)` 고정. 내부 PostGIS도 `ST_MakePoint(lon, lat)` 순서(SKILL.md §4-5).

## Readiness 자동화 (`addr-kr validate`)

```bash
addr-kr validate all
```

본 명령은 다음을 한 번에 수행한다:

- 마스터 11개 + 보조 2개 + MV 1개 존재 여부
- 시도별 row count 분포가 정상 범위인지 (이상치 경고)
- `tl_spbd_buld.bd_mgt_sn` unique 검사
- `mv_geocode_target`의 `ent_pt_4326` null/한국 외 좌표 검출
- `pg_trgm`, `unaccent`, `postgis` 확장 설치 여부

실패 항목이 있으면 종료 코드 1로 끝나고 `--json`으로 출력 가능 → CI/관리 UI에서 수집.
