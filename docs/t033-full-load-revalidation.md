# T-033 전국 full-load 성능 재검증

본 문서는 T-032에서 세종특별자치시·경상남도 2개 시도만 검증했던 성능 튜닝 결과를 전국 17개 시도 실제 데이터로 다시 검증한 기록이다. 목적은 "성공/실패"만 확인하는 것이 아니라, 다음 튜닝 PR(T-034, T-035)이 비교할 수 있는 기준선을 남기는 것이다.

## 범위

이번 작업은 다음을 확인한다.

1. 빈 Docker PostGIS DB에 DDL/Alembic 현재 스키마를 적용한다.
2. 실제 `data/juso` 전체분을 사용해 텍스트 정본 3종과 전자지도 SHP 9개 보조 레이어를 전국 단위로 적재한다.
3. `resolve_text_geometry_links()`와 `mv_geocode_target` swap refresh를 수행한다.
4. C1~C10 정합성, geocode/reverse/search/zipcode smoke test, data-quality sample export를 실행한다.
5. 단계별 경과 시간, 시스템 상태, row count, 관찰된 병목을 문서화한다.

T-034는 본 문서의 SHP 기준선, 특히 `TL_SPRD_INTRVL`과 `TL_SPBD_BULD` 적재 시간을 기준으로 튜닝 전후를 비교한다. T-035는 MV refresh/swap 시간을 기준으로 비교한다.

## 실행 환경

| 항목 | 값 |
|------|----|
| 실행일 | 2026-05-25 |
| Git commit | `b1727f0` (`main` merge commit, PR #19 이후) |
| 작업 브랜치 | `codex/t033-full-load-revalidation` |
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | AMD Ryzen 7 7840HS, 16 logical cores |
| 메모리 | 29GiB total, 실행 전 available 약 27GiB |
| ext4 여유 공간 | `/dev/sdd` 1007G 중 791G available |
| NTFS 데이터 공간 | `/mnt/f` 932G 중 267G available |
| Docker DB | `kor-travel-geo-t027-db-1`, `postgis/postgis:16-3.5`, host port `15432` |
| 테스트 DB | `kor_travel_geo_t033` |
| ext4 데이터 경로 | `/home/digitie/kor-travel-geo-data` |
| 원본 NTFS 데이터 경로 | `/mnt/f/dev/kor-travel-geo/data/juso` |
| 로그 경로 | `artifacts/t033-full-load-20260525_224643/` (git ignore) |

## 입력 데이터

| 자료 | 기준월 | 경로 | 처리 |
|------|--------|------|------|
| 도로명주소 한글 전체분 | 202603 | `juso/202603_도로명주소 한글_전체분` | `rnaddrkor_*.txt` 17개 적재 |
| 위치정보요약DB 전체분 | 202604 | `juso/202604_위치정보요약DB_전체분.zip` | `entrc_*.txt` ZIP member 적재 |
| 내비게이션용DB 전체분 | 202604 | `juso/202604_내비게이션용DB_전체분` | `match_build_*.txt`, `match_rs_entrc.txt` 적재 |
| 도로명주소 전자지도 | 파일별 제공 기준 | `juso/도로명주소 전자지도` | ADR-012 보조 SHP 9개 레이어 적재 |

자료별 기준월이 서로 다르므로 C10은 동월 전체분 검증이 아니라 "현재 로컬 보유 데이터 조합" 검증으로 해석한다.

## 실행 명령

```bash
PGPASSWORD=addr createdb -h localhost -p 15432 -U addr kor_travel_geo_t033

ARTIFACT_DIR=artifacts/t033-full-load-20260525_224643
PATH=/home/digitie/dev/kor-travel-geo/.venv/bin:$PATH \
DATA_DIR=/home/digitie/kor-travel-geo-data \
JUSO_YYYYMM=202603 \
LOCSUM_YYYYMM=202604 \
NAVI_YYYYMM=202604 \
KTG_DB_PORT=15432 \
KTG_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t033 \
KTG_PG_STATEMENT_TIMEOUT_MS=1800000 \
TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  /usr/bin/time -v bash scripts/fullload_test.sh 2>&1 | tee "$ARTIFACT_DIR/fullload.log"
```

## 실행 결과

전체 실행은 성공했다. `/usr/bin/time -v` 기준 wall clock은 **4시간 8분 2초**, 최대 RSS는 **187,964KB**, exit status는 `0`이었다.

| 단계 | 결과 | 경과 시간 | 메모 |
|------|------|-----------|------|
| DDL/init-db | 완료 | 약 4초 | schema/index/empty MV 생성 |
| 도로명주소 한글 | 완료 | 텍스트 3종 합산에 포함 | `tl_juso_text` loader 출력 `6,416,637`행 |
| 위치정보요약DB | 완료 | 텍스트 3종 합산에 포함 | loader 출력 `6,405,094`행, 최종 count는 중복/충돌 반영 후 `6,405,091`행 |
| 내비게이션용DB | 완료 | 별도 산출 필요 | `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830` |
| 텍스트 3종 합계 | 완료 | 1,098초 | 18분 18초 |
| SHP 17개 시도 × 9개 레이어 | 완료 | 약 3시간 37분 32초 | `TL_SPRD_INTRVL`, `TL_SPBD_BULD`가 지배. 총 153 layers |
| 후처리 링크 | 완료 | 약 2분 32초 | `resolve_text_geometry_links()` transaction-local 30분 timeout으로 성공 |
| MV swap refresh | 완료 | 약 2분 28초 | `refresh mv --swap` 성공 |
| row count | 완료 | 약 19초 | 대형 테이블 count 포함 |
| C1~C10 consistency | 완료 | 약 6분 48초 | `severity_max=ERROR`; C2/C4/C6/C7은 기존 실제 데이터 오류 유지 |
| smoke test | 완료 | 약 1초 | geocode/reverse/search/zipcode 모두 `OK` |
| data-quality sample export | 완료 | 1분 20.41초 | C2/C4/C6/C7 CSV 8개 생성, 최대 RSS 80,272KB |

SHP 3시간 37분 32초는 `fullload.log`의 Phase 3 시작/종료 timestamp 차이를 기준으로 읽은 값이다. 전체 wall clock에서 다른 phase를 산술 차감한 추정값이 아니므로, timestamp 단위 반올림과 shell 출력 flush 시점 때문에 1분 안팎의 오차가 있을 수 있다. T-036 후속 보강으로 `scripts/fullload_test.sh`는 다음 클린 로드부터 `juso`, `locsum`, `navi`, SHP, 링크 해소, MV swap을 각각 초 단위로 출력한다.

이번 수치는 단발 실행 결과다. 같은 Docker DB를 idle 상태로 두고 실행했지만 OS page cache, 직전 DB 작업, 다른 WSL 프로세스에 따른 분산은 별도로 추정하지 않았다. T-027 최종 클린 로드에서는 같은 스크립트의 phase별 timer 출력을 그대로 붙여 단발 측정 한계를 더 명확히 남긴다.

## 최종 row count

| 테이블 | 행 수 |
|--------|------:|
| `tl_juso_text` | 6,416,637 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `mv_geocode_target` | 6,416,637 |
| `tl_scco_ctprvn` | 17 |
| `tl_scco_sig` | 255 |
| `tl_scco_emd` | 5,067 |
| `tl_scco_li` | 15,161 |
| `tl_kodis_bas` | 34,516 |
| `tl_sprd_manage` | 875,221 |
| `tl_sprd_intrvl` | 16,993,167 |
| `tl_sprd_rw` | 1,482,679 |
| `tl_spbd_buld_polygon` | 10,687,732 |

최종 DB 크기는 `pg_database_size('kor_travel_geo_t033')` 기준 약 **26GB**였다. `postal_pobox`, `postal_bulk_delivery`는 로컬 ext4 mirror에 epost 파일이 없어 이번 실행에서 적재하지 않았다.

## 링크 해소율

| 대상 | 전체 | `bd_mgt_sn` 해소 | 해소율 |
|------|------:|-----------------:|-------:|
| `tl_locsum_entrc` | 6,405,091 | 2,906,372 | 45.3760% |
| `tl_navi_entrc` | 12,830 | 11,421 | 89.0179% |

`tl_locsum_entrc` 해소율이 낮은 것은 C3 WARN의 직접 원인이다. 위치정보요약DB 원천의 natural key가 정본 텍스트와 완전히 맞지 않는 행이 많으므로, 후속에서는 누락 원인을 `rncode_full`/건물번호/법정동 코드별로 쪼개 확인한다.

## 정합성 결과

`ktgctl validate consistency --scope full` 결과 `severity_max=ERROR`였다. 이는 현재 실제 원천 조합에서 기대하던 잔여 데이터 품질 이슈이며, full-load 자체 실패로 보지 않는다.

| Case | Severity | Count | 주요 metric |
|------|----------|------:|-------------|
| C1 | WARN | 32,531 | 텍스트에만 존재 |
| C2 | ERROR | 34,699 | `missing_text=34,118`, `missing_resolve_key=581` |
| C3 | WARN | 3,510,265 | 대표 출입구 미해소, ratio 0.547057 |
| C4 | ERROR | 3,415 | `over_50m=3,415`, `over_500m=16`, `p95_m=3.82`, `p99_m=15.50` |
| C5 | WARN | 202 | `over_10m=202` |
| C6 | ERROR | 803 | `outside_polygon=803`, `missing_polygon=0` |
| C7 | ERROR | 6,817 | `outside_polygon=6,817`, `missing_polygon=0` |
| C8 | WARN | 24,471 | 같은 도로명 100m 밖 |
| C9 | OK | 0 | PNU 형식 오류 없음 |
| C10 | OK | 0 | `load_manifest` 대상 table의 `source_yyyymm` distinct count 기준. 이 수동 CLI 실행에서는 manifest 기반 비교 대상이 0건이라 OK로 해석한다 |

C10은 현재 row-level `source_yyyymm` 컬럼을 전수 비교하지 않고, `load_manifest.table_name IN ('tl_juso_text', 'tl_locsum_entrc', 'tl_navi_buld_centroid', 'tl_navi_entrc', 'tl_spbd_buld_polygon')`에 기록된 `source_yyyymm`의 distinct count만 본다. 따라서 `JUSO_YYYYMM=202603`, `LOCSUM_YYYYMM=202604`, `NAVI_YYYYMM=202604`처럼 자료 기준월이 섞인 이번 수동 실행에서 C10 `OK 0`은 "모든 원천 row 기준월이 같다"는 뜻이 아니라 "manifest 기준으로 비교할 위반 row가 없었다"는 뜻이다.

## Data-quality export

전국 DB에서 `ktgctl validate data-quality-samples --cases C2,C4,C6,C7 --limit 20`을 별도로 실행해 CSV 8개를 생성했다.

| 파일 | 핵심 결과 |
|------|-----------|
| `c2_missing_key_summary.csv` | `rows=581`, `missing_rds_sig_cd=581`, 나머지 resolve key 결측 0 |
| `c4_distance_buckets.csv` | `0-50=2,887,827`, `50-100=2,847`, `100-500=552`, `500+=16` |
| `c6_region_summary.csv` | 상위 region: `54002=49`, `48700=23`, `54004=15` |
| `c7_region_summary.csv` | 상위 region: `48121103=216`, `28260101=167`, `41273104=165` |

T-032의 전국 이전 DB 결과와 동일한 핵심 수치가 재현됐다. PR #19에서 보강한 temp table transaction 경로도 전국 DB에서 정상 동작했다.

## Smoke test

스크립트 내 smoke test는 모두 통과했다.

| 항목 | 결과 |
|------|------|
| geocode | `서울특별시 종로구 자하문로 94` → `OK`, point `(126.97040554796257, 37.58441543603026)` |
| reverse | geocode point 기준 `OK`, result count 10 |
| search | `자하문로` → `OK`, total 1,701, first `서울특별시 종로구 자하문로 94` |
| zipcode | 같은 주소 → `OK`, first `03047` |

## 중간 관찰

- `TL_SPRD_INTRVL`은 geometry 없는 interval 테이블인데도 GDAL `VectorTranslate` 경로에서 `INSERT INTO "tl_sprd_intrvl" ... VALUES ...` 형태로 관측됐다. `PG_USE_COPY=YES`가 이 레이어에 기대대로 적용되지 않는 것으로 보이며, T-034의 최우선 튜닝 후보로 둔다.
- 경기도 `TL_SPRD_INTRVL` 한 레이어만 약 24분 이상 걸렸다. 텍스트 정본 3종 전체가 1,098초였으므로, SHP interval 레이어가 전국 full-load의 주요 병목이라는 판단 근거가 충분하다.
- `TL_SPBD_BULD`도 `INSERT INTO "tl_spbd_buld_polygon" ...` 형태로 관측됐다. geometry 포함 대형 레이어라 비용은 예상되지만, COPY 또는 GDAL 옵션 검증 대상이다.
- `tl_navi_entrc=12,830`은 `tl_navi_buld_centroid=10,687,317` 대비 매우 작다. 현재 문서는 적재 결과만 기록했으며, 원천 `match_rs_entrc.txt` row count와 loader 적재 row count의 1:1 일치 여부는 후속 클린 로드나 별도 원천 검증에서 확인한다.
- `TL_SPRD_RW`, `TL_SPBD_BULD`, 일부 행정경계 SHP에서 winding order 자동 보정 경고가 반복됐다. GDAL이 자동 보정했고 적재는 계속 진행됐다.
- SHP 적재 중 DB CPU는 대체로 30~50% 수준, 메모리는 4~9GiB 수준이었다. C4/C5 정합성 검증에서는 CPU가 2~3 core 수준, 메모리가 약 14GiB까지 올라갔다. 전체적으로 메모리 포화보다는 로더 append 경로와 WAL/쓰기 비용이 병목으로 보인다.

## 후속 작업 연결

- T-034: `TL_SPRD_INTRVL` 전용 COPY 로더 또는 GDAL 옵션 분리 실험. 가능하면 경기도 단일 시도를 benchmark fixture로 사용하고, 전국 full-load에서의 예상 절감 시간을 추정한다.
- T-035: 본 실행의 MV swap refresh 시간을 기준선으로 삼아 `REFRESH CONCURRENTLY`와 shadow swap을 비교한다.
- T-037: `TL_SPBD_BULD` 등 geometry 포함 대형 SHP 레이어의 GDAL append/COPY/staging table 전략을 별도 튜닝 후보로 둔다.
- T-027: 마지막 전체 검증 단계에서는 DB를 삭제하고 처음부터 다시 로드해 T-034/T-035 개선분이 전체 파이프라인에서도 정상 동작하는지 확인한다.
