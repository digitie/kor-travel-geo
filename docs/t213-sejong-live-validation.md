# T-213 (소형) — 세종 실데이터 전 구간(end-to-end) 검증 (T-109 소스 파이프라인)

**상태:** 통과 — 실 가동 PostGIS + 실 세종 데이터 + 실 GDAL 로더로 신규 소스 파이프라인 전 구간 검증 완료.
**날짜:** 2026-06-15
**브랜치:** `agent/claude-t213-sejong-live` → PR #165 머지(`3fb4ea5`)
**실행 스크립트:** `scripts/run_sejong_live_pipeline.py` (멱등, DSN/ZIP 파라미터, 자체 정리, 파괴적 작업 가드)

이 작업은 신규(T-109) 소스 업로드/매치셋/리빌드 파이프라인이 **실제 세종특별자치시 전자지도
SHP 아카이브**를 등록→검증→활성화→리빌드 브리지→**실제 로더 적재**까지 끝까지 굴러가는지를
LIVE DB에 증명하는 *소형* end-to-end 검증이다. 전국 TXT 카테고리(juso/locsum/navi) +
full serving 프로파일은 본 검증의 범위가 아니다(아래 "전국 caveat" 참조 — 그게 T-213 proper).

## 실행 환경

| 항목 | 값 |
|------|----|
| Live DB | `kor_travel_geo` (container `ktg-t210-db`), `localhost:15434` |
| DSN | `postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo` |
| PostGIS | 3.5.2 |
| GDAL | 3.12.2 (`osgeo.gdal` Python binding, WSL venv `~/ktgvenv`) |
| 실 데이터 | `/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 전자지도/202604/세종특별자치시.zip` (26,926,379 bytes) |
| 기준월 | `202604` (electronic_map = `NAVI_YYYYMM`/`LOCSUM_YYYYMM` 기준월) |

실행 (스크래치 DB 전용 — 파괴적):

```bash
cd /mnt/f/dev/kor-travel-geo-claude
KTG_TEST_PG_DSN='postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo' \
    ~/ktgvenv/bin/python scripts/run_sejong_live_pipeline.py \
    --allow-destructive --confirm 'TRUNCATE-SEJONG-RUNBOOK kor_travel_geo'   # 멱등, 끝에 자체 정리
# 검사용으로 행을 남기려면 뒤에 --keep 추가.
```

> 런북은 serving SHP 테이블을 TRUNCATE하고 활성 match set을 retire하므로, `--allow-destructive`
> 와 `--confirm 'TRUNCATE-SEJONG-RUNBOOK <current_database()>'`(DB 이름 일치) 없이는 실행을 거부한다.
> 기본 DSN은 없다(`KTG_TEST_PG_DSN` 또는 `--dsn` 필수). 실행 직전 활성 match set을 기록하고 정리
> 단계에서 복구하므로 기존 활성 구성을 원래대로 되돌린다(`--keep` 시는 제외).

## 실제로 굴린 전 구간 경로

순서대로 **infra 서비스 레이어를 직접(in-process) 호출**한다(uvicorn/SSE 불필요).

1. **schema apply (멱등)** — `iter_sql_statements(SCHEMA_SQL)` + `INDEX_SQL`을 statement 당
   savepoint로 실행, 이미 존재하는 제약(`42710`/`42P07`)은 무시. (이 LIVE DB는 이미 스키마가
   적용돼 있어 `ALTER TABLE ... ADD CONSTRAINT fk_ops_dataset_snapshots_source_match_set`가
   bare DDL로 재실행 시 `DuplicateObject`를 던지므로 tolerate 처리.)
2. **register** (`infra/source_upload_repo.py` + `infra/source_group_service.py`):
   - `SourceUploadSessionRepository.create_session` 로 `electronic_map_full`(multi_part) 세션 생성,
     `record_part`로 세종 슬롯(part_key=`36`)을 완료 part로 기록.
   - 실 ZIP의 **실제 SHA-256 + size** 계산(`sha256_file`, `Path.stat`).
   - **실제 구조 검증**: `scan_part_manifest`(zipfile 멤버 스캔) → `_validate_layer_part`(전자지도
     11개 master layer + `.shp/.shx/.dbf` sidecar 완전성). 세종 part 결과 = **`warning`**
     (11개 layer 모두 존재, sidecar 완비, layer별 `.prj`만 없음 — ZIP은 공용 `GRS80_UTMK.prj` 1개만
     포함 → "EPSG:5179 가정" 경고).
   - `SourceGroupRegistrar.register(storage_kind="local", bucket=None, …)` → `ops.source_files`의
     `storage_uri = local://<실 ZIP 경로>` (T-076 local storage). `ops.source_file_groups` /
     `source_files` / `source_file_members`(layer별 member 행) / `source_file_validations`(scope=group)
     실 행 생성. `recompute_group_aggregates`가 그룹을 **`available`**(validation_state=`warning`)로 승격.
   - **실제 group_sha256** = `7634beb4000e5a388f76be2f2db72c3b960014390e52c004defe8bed4df200c9`
     (자식 `(part_kind, part_key, sha256, size)` 의 canonical SHA-256 — 매 실행 동일 = 결정적).
3. **match set** (`infra/source_match_set_service.py`) — `custom` 프로파일(required 카테고리 없음):
   `create_match_set`(item: electronic_map_full / build_required / load_order=1 / 위 그룹) →
   `validate_match_set`(action=`validate_draft`, state=`validated`, `source_set_hash` 계산) →
   `activate_match_set`(state=`active`, advisory-lock atomic swap).
4. **rebuild bridge** (`infra/source_rebuild_service.py`) — `prepare_rebuild(msid)`가 start
   precondition·stale-job sweep·integrity 게이트 입력을 거쳐 **실제 `full_load_batch` payload**를
   조립. electronic_map_full → `_CATEGORY_TO_LOAD_KIND` → child `{"kind":"shp_polygons_load",
   "payload":{path, source_yyyymm, source_file_group_id, group_sha256, storage_uris, …}}`,
   root payload에 `source_match_set_id`/`source_set`/`staging_dir` 포함.
5. **실 로더 적재** — 조립된 child가 가리키는 staging dir
   (`rebuild_staging/<msid>/electronic_map_full/세종특별자치시/36000/TL_*.shp`)로 ZIP을 풀고,
   `shp_polygons_load` 핸들러(`api/app.py`의 `shp`)가 호출하는 **바로 그 로더**
   `loaders.shp.polygons_loader.load_shp_polygons(engine, <시도 dir>, mode="full",
   source_yyyymm="202604")`를 실행 → GDAL `VectorTranslate`(EPSG:5179, PROMOTE_TO_MULTI,
   `PG_USE_COPY=YES`, `SHAPE_ENCODING=CP949`) + 건물폴리곤 staging→INSERT + 도로구간 DBF→COPY.
   반환 layer 수 = **9**.
6. **verify** — 9개 serving SHP 테이블 row count(전부 > 0), 각 테이블 샘플 행
   (geometry type / SRID 포함), `ops.dataset_snapshots`에 `source_match_set_id` 정본 FK 기록 후
   링크 검증.

## 실제 결과 수치

```
[2] register: group state=available  validation_state=warning  structure outcome=warning
    group_sha256 = 7634beb4000e5a388f76be2f2db72c3b960014390e52c004defe8bed4df200c9
[3] match-set: validate action=validate_draft state=validated → activate state=active
[4] rebuild bridge: child kind=shp_polygons_load
    loader returned 9 layers in ~29s
[5] serving SHP table row counts (세종특별자치시, 202604):
```

| 테이블 | 행 수 | geometry |
|--------|------:|----------|
| `tl_scco_ctprvn` | 1 | MultiPolygon/5179 |
| `tl_scco_sig` | 1 | MultiPolygon/5179 |
| `tl_scco_emd` | 33 | MultiPolygon/5179 |
| `tl_scco_li` | 117 | MultiPolygon/5179 |
| `tl_kodis_bas` | 155 | MultiPolygon/5179 |
| `tl_sprd_manage` | 4,207 | MultiLineString/5179 |
| `tl_sprd_intrvl` | 100,009 | (DBF-only, no geom) |
| `tl_sprd_rw` | 7,429 | MultiPolygon/5179 |
| **`tl_spbd_buld_polygon`** | **55,819** | MultiPolygon/5179 |
| **합계** | **167,771** | |

샘플 행 (실값):

```
tl_spbd_buld_polygon: bd_mgt_sn=4473034044101480002028865 sig_cd=36110 buld_mnnm=57 buld_slno=1 ST_MultiPolygon srid=5179
tl_sprd_manage:       sig_cd=36110 rds_man_no=1 rn_cd=4574305 ST_MultiLineString srid=5179
tl_sprd_rw:           sig_cd=36110 rw_sn=1 ST_MultiPolygon srid=5179
tl_sprd_intrvl:       sig_cd=36110 rds_man_no=1 bsi_int_sn=45438
```

`sig_cd=36110`(세종특별자치시 행정구역 코드)로 적재된 데이터가 실제 세종임을 확인.

**정본 FK:** `ops.dataset_snapshots` 행을 `state='validated'`, `source_match_set_id=<msid>`,
`source_set`=리빌드 plan의 source_set, `row_counts`=위 카운트로 기록하고
`source_match_set_id` 링크를 재조회로 검증 → **linked=True**. (스키마상
`fk_ops_dataset_snapshots_source_match_set` FK가 실제로 존재함을 schema-apply 단계에서 확인.)

**타이밍:** register ~0.2s, match-set create+validate+activate <0.1s, **로더 적재 ~29s**,
전체 ~34s (초기 `--keep` 첫 실행 36.4s 포함 다회 측정, 로더 구간이 지배적).

**멱등성:** 2회 연속 실행에서 group_sha256 동일(`7634beb4…`), row count 동일(167,771), FK linked
동일. `source_set_hash`는 실행마다 새 그룹 UUID를 포함하므로 달라지는 게 정상
(예: `ffa780f9…`, `331bf922…`, `99ca77f9…`). 실행 시작 시 자기 소유 행을 마커로 선삭제하고
serving 테이블을 TRUNCATE하므로 반복 실행 가능. `--keep` 미지정 시 종료 직전 자기 행 + staging
디렉터리까지 정리(append-only인 `ops.audit_events`는 의도적으로 보존 — 실행당 4 action 기록).

## 무엇이 완전히 굴렀고 / 어떤 우회가 있었나

**완전히 실행(실 데이터/실 서비스):** schema apply, upload-session create/record_part,
register(실 sha256/size/group_sha256, 실 SHP layer/sidecar validator, 실 member 행),
match-set create/validate/activate(custom), rebuild `prepare_rebuild`(실 `full_load_batch`
payload 조립), **실 GDAL 로더 적재**(9 layer, 167,771 행), serving row/샘플 검증,
dataset_snapshot 정본 FK 기록+검증.

**우회 2가지 (정확히 문서화):**

1. **`full_load_batch` JobQueue 핸들러 부재.** `full_load_batch`는 enqueue 시점에 자식으로
   펼쳐지는 batch-root 마커일 뿐, 디스패치되는 핸들러 kind가 아니다(`api/_jobs.py`/`infra/batch.py`).
   따라서 리빌드 서비스로 **payload를 조립**한 뒤, 그 payload가 가리키는 staging dir를 만들고
   `shp_polygons_load` 핸들러가 부르는 **동일 로더** `load_shp_polygons`를 직접 호출했다.
   결과적으로 "신규 파이프라인이 쓰는 그 로더로 실 세종 SHP → serving 테이블"은 그대로 증명된다.
   리빌드 서비스도 ZIP 추출은 하지 않고(아카이브가 staging에 이미 materialize됐다고 가정)
   본 런북이 그 materialize 단계를 수행한다 — 이는 운영 리빌드 핸들러가 RustFS download로
   하는 일과 동치(여기선 local storage이므로 ZIP을 staging에 풀어줌).
2. **단일 시도 구조 검증 스코프.** 17-시도 `validate_group_manifest`는 단일 시도 업로드에 대해
   **올바르게 `failed`**(나머지 16개 시도 missing)를 반환한다. 그래서 런북은 그룹 구조 결정을
   **실제 per-part SHP layer/sidecar validator**(`_validate_layer_part` over 실 ZIP 멤버)를
   존재하는 단일 시도에만 적용해 구성한다(outcome=`warning`). 검증 로직 자체는 진짜이고,
   다만 일부러 1개 시도만 적재하므로 17-시도 커버리지 게이트를 우회한 것이다.

## 전국 검증 범위 — T-213 proper(후속)

- 단일 시도로는 `serving_minimal` 프로파일을 만족할 수 없다(전국 juso/locsum/navi TXT +
  electronic_map 6개 build 카테고리 + 17-시도 커버리지 필요). 그래서 본 검증은 `custom`
  프로파일(required 카테고리 없음)로 electronic_map 단일 그룹만 활성화했다.
- **T-213 proper에서 추가로 필요한 것:**
  1. 전국 TXT 카테고리(`roadname_hangul_full`/`locsum_full`/`navi_full`)의 register + 로더
     (juso_text/locsum/navi) 적재 → `tl_juso_text`/`tl_locsum_entrc`/`tl_navi_*` 채우기.
  2. electronic_map 17-시도 전체 업로드(`validate_group_manifest`가 `passed/warning`이 되도록).
  3. `serving_minimal`(또는 `recommended`) 프로파일 match-set으로 validate/activate.
  4. 실제 `full_load_batch` 경로(JobQueue + consistency_check 게이트 + mv_refresh swap +
     serving_release/dataset_snapshot)를 running app/worker로 구동 — 본 런북의 우회(직접 로더 호출)
     없이 DAG 전체를 굴리는 것.
- 즉 본 문서는 "신규 파이프라인의 register→match-set→rebuild-bridge→**실 SHP 로더 적재**"
  슬라이스가 실 데이터로 동작함을 증명하며, MV/consistency/release 게이트와 전국 텍스트 카테고리는
  T-213 proper로 남는다.

## ruff

```
$ ~/ktgvenv/bin/ruff check scripts/run_sejong_live_pipeline.py
All checks passed!
```
