# 지오코딩 준비 상태

`kor-travel-geo`이 정상 동작하려면 PostgreSQL + PostGIS 환경, 텍스트 정본 + 좌표 원천 + 보조 도형 적재, MV refresh, ANALYZE까지 끝난 상태가 필요하다. serving 정본은 텍스트(`tl_juso_text`)이고 SHP는 도형 보조다(ADR-007, ADR-012). 본 문서는 그 체크리스트와 알려진 빈틈을 정리한다.

> 이전(v1) SpatiaLite 기반 readiness 기준은 `v1` 브랜치 문서에서 본다. `main`은 PostgreSQL + PostGIS 기준만 다룬다(ADR-001).

## 강한 입력 데이터

| 자료 | 역할 |
|------|------|
| 도로명주소 한글_전체분 (텍스트) | `tl_juso_text` — 도로명/지번/행정/우편번호 정본. 지오코딩 1차 매핑 |
| 위치정보요약DB (텍스트) | `tl_locsum_entrc` — 대표 출입구 좌표. serving 좌표 1순위 |
| 도로명주소 출입구 정보 (텍스트) | `tl_roadaddr_entrc` — direct 출입구 좌표. same-month일 때만 fallback |
| 내비게이션용DB (텍스트) | `tl_navi_buld_centroid`/`tl_navi_entrc` — 출입구 없는 건물의 centroid fallback / 진입점 |
| 도로명주소 전자지도 (시도별 SHP, 도형 전용) | `tl_spbd_buld_polygon`, `tl_scco_*`, `tl_sprd_*` — 정합성 검증·polygon 응답용 도형 |
| 기초구역 (`tl_kodis_bas`) | 우편번호 polygon. 역지오코딩의 zipcode lookup |
| 사서함 (`postal_pobox`) | 우편번호 4단계 우선순위의 한 축 |
| 다량배달처 (`postal_bulk_delivery`) | 같은 `bd_mgt_sn`에 별도 우편번호가 필요한 케이스 |
| 외부 API (vworld, juso) | 폴백 (`fallback="api"`) 및 자동 다운로드(epost) |

## 환경 readiness 체크리스트

PC 개발의 Git source of truth는 NTFS worktree(`/mnt/f/dev/kor-travel-geo-*`)이고, 테스트와 장기 실행은 WSL ext4 테스트 미러로 복사한 뒤 수행한다(AGENTS.md, ADR-041 참조). 대용량 Juso 원천은 NTFS 공용 루트(`/mnt/f/dev/geodata/juso`) 아래에 두며, 아래 명령의 데이터 경로는 ext4 테스트 미러에서 `data -> /mnt/f/dev/geodata` 심볼릭 링크 또는 절대경로로 해석한다.

1. **시스템 GDAL 설치** — `sudo apt install libgdal-dev gdal-bin`. `gdal-config --version`으로 버전 확인 후 Python 바인딩 핀: `pip install "gdal==$(gdal-config --version)"`. 세부 절차는 `docs/dev-environment.md` 참조 (ADR-008).
2. **PostgreSQL 16 + PostGIS 3.4** 설치 및 기동
3. `pg_trgm`, `unaccent` 확장 설치
   ```sql
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS unaccent;
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
4. `Settings.pg_dsn` 설정 (`postgresql+psycopg://...`)
5. `ktgctl init-db`(또는 `alembic upgrade head`)로 스키마·확장·인덱스·빈 MV 적용 (텍스트 정본 + 좌표 원천 + 보조 도형 + 메타 + MV 정의)
6. NTFS의 공용 데이터 디렉토리를 ext4 테스트 미러에서 참조: `ln -s /mnt/f/dev/geodata data`
7. 17개 시도 원천 적재 (`ktgctl load all-sidos --juso ... --locsum ... --navi ... --shp-root ... --yyyymm 202605`). 텍스트 정본(`tl_juso_text`) + 좌표 원천(`tl_locsum_entrc`, `tl_navi_*`) + SHP 도형 보조를 한 배치로 적재한다.
8. `ktgctl load pobox <pobox.txt>`, `ktgctl load bulk <bulk.txt>` (또는 `ktgctl load epost`로 다운로드+적재)
9. `ktgctl refresh mv` → `mv_geocode_target`(및 `mv_geocode_text_search` helper) 갱신 + `ANALYZE`. 분기 풀로드는 `ktgctl refresh mv --swap`(shadow MV rename swap).
10. `ktgctl validate consistency` — 텍스트 정본 ↔ SHP polygon 정합성(C1~C10) 검사. 필요 시 `ktgctl validate data-quality-samples`로 C2/C4/C6/C7 리뷰용 CSV 생성.

## 검증 시나리오

- 17개 시도 전체 적재 후 `tl_juso_text` row count 비교 (시도별 합과 일치하는지)
- `mv_geocode_target` 행 수 = `tl_juso_text` 건물 수 (좌표 출처는 `pt_source`로 entrance/centroid 분포 확인)
- 도로명·지번 매칭 쿼리에 `EXPLAIN(ANALYZE)`로 인덱스 사용 확인
- 샘플 주소 100건에 대해 vworld 원응답과 `AsyncAddressClient.geocode` 결과 비교 (좌표 오차 < 10m 비율 측정)
- 역지오코딩: 임의 (lon, lat) 1,000건을 입력해 `/v1/address/reverse`가 출입구·centroid hit / 국가지점번호 context-only / NOT_FOUND 비율을 측정

## 알려진 빈틈

- **GDAL Python binding 환경 의존성**: 시도별 SHP 적재는 GDAL 3.8+ 필요. 운영은 Docker 이미지로 표준화 권장(ADR-005).
- **CP949 디코딩 누락 위험**: `gdal.OpenEx(..., open_options=["ENCODING=CP949"])`를 항상 명시. 누락 시 한글 깨짐 그대로 적재되는데 인덱스도 깨진 키로 만들어지므로 즉시 발견하기 어렵다.
- **`MVM_RES_CD` 코드 신규 도입**: 데이터셋이 시간 흐름에 따라 새 코드를 추가할 수 있다. 매핑은 `load_codes` 테이블 또는 settings에서 hot-fix 가능(SKILL.md §4-6).
- **외부 API 쿼터 침범**: vworld/juso 일 한도 도달 시 자동 fallback 비활성화 로직이 필요(`docs/architecture/external-apis.md` 호출 정책).
- **fuzzy 매칭 임계값**: `pg_trgm.similarity_threshold = 0.42`로 검증되어 있다. 0.3 미만은 noisy, 0.5 이상은 reject 과다. 데이터셋 갱신 시 재검증 권장.
- **좌표계 혼동**: 외부 인터페이스는 `(lon, lat)` 고정. 내부 PostGIS도 `ST_MakePoint(lon, lat)` 순서(SKILL.md §4-5).

## Readiness 자동화 (`ktgctl validate`)

```bash
ktgctl validate consistency
ktgctl validate data-quality-samples --cases C2,C4,C6,C7
```

`validate consistency`는 텍스트 정본과 SHP polygon을 교차 검증하는 C1~C10 케이스(ADR-016)를 실행한다. 대표적으로:

- C1/C2: `tl_juso_text` ↔ `tl_spbd_buld_polygon` BD_MGT_SN 차집합 (텍스트/도형 누락)
- C3: 출입구 0개 건물 비율 (`tl_locsum_entrc` 대표 출입구 + same-month direct 출입구 기준, centroid fallback 흡수)
- C4: serving 출입구 좌표 ↔ 건물 polygon 거리
- C6/C7: 좌표 ↔ 우편번호(`tl_kodis_bas`)/행정동(`tl_scco_emd`) polygon 포함·코드 일치
- C9: `tl_juso_text.pnu` 19자리 형식 검증
- C10: 테이블별 `source_yyyymm` 혼합 기준월 검사

결과는 `load_consistency_reports`에 구조화 JSON으로 저장되고 `model_dump_json()`으로 출력된다. `severity_max == "ERROR"`이면 배치/swap gate에서 차단된다. `validate data-quality-samples`는 C2/C4/C6/C7 리뷰용 CSV를 `artifacts/`에 생성한다(운영 gate 아님).
