# T-109: 백업 원천 파일 업로드·매칭·검증 관리 고도화 설계

## 상태

- 상태: 문서화 완료, 구현 대기
- 기준 요청일: 2026-06-14
- 기준 브랜치: `codex/backup-upload-advanced-design`
- 관련 문서:
  - `docs/backup-restore-source-inventory.md`
  - `docs/source-data-accuracy-review.md`
  - `docs/t045-source-set-load-ux.md`
  - `docs/t046-db-backup-restore.md`
  - `docs/t076-rustfs-upload-storage.md`
  - `docs/t049-ops-metadata-schema.md`
  - `docs/data-model.md`
- 관련 기존 코드:
  - `src/kortravelgeo/dto/admin.py`
  - `src/kortravelgeo/infra/source_set.py`
  - `src/kortravelgeo/infra/uploads.py`
  - `src/kortravelgeo/infra/rustfs.py`
  - `src/kortravelgeo/api/routers/admin.py`
  - `kor-travel-geo-ui/components/admin/LoadConsole.tsx`

## 한 줄 결론

기존 T-045/T-076의 upload set은 "파일을 받아 source kind를 추정한 뒤 적재 계획을 만든다"에 가깝다. T-109에서는 이 흐름을 **카테고리별 명시 업로드, 사용자가 확정한 기준년월, DB에 저장되는 원천 파일 registry, RustFS object 정합성 검증, 사용자가 조합하는 source match set, optional 검증 자료** 중심으로 재설계한다. 업로드 파일 자체는 압축파일 원본을 RustFS에 장기 보관하고, DB는 "무엇이 정상 업로드되어 어떤 match set에 쓰였는지"의 정본이 된다.

## 요구사항 반영 매트릭스

| 번호 | 요구사항 | 설계 반영 |
|------|----------|-----------|
| 1 | 파일 업로드를 파일 카테고리별로 명시적으로 분리 | `/admin/source-files` 또는 `/admin/load`의 새 source registry 영역에서 카테고리 slot별 업로드만 허용한다. 자동 source kind 추정은 보조 표시일 뿐, 사용자가 고른 카테고리를 덮어쓰지 않는다. |
| 2 | 기준년월은 사용자가 직접 입력, 파일명 추정은 UI 기본값만 | 모든 업로드는 `user_yyyymm` 필수. `inferred_yyyymm`은 기본값과 경고 표시용으로만 사용한다. 최종 저장과 match set은 `user_yyyymm`을 사용한다. |
| 3 | 업로드 파일 정보 DB 관리 | `ops.source_files`, `ops.source_file_members`, `ops.source_file_validations`를 추가한다. 기존 `upload-set.json`은 작업 캐시로 남기되 정본이 아니다. |
| 4 | 임시 디렉터리 저장 → 압축 해제/구조 검증 → 압축파일 원본을 RustFS 저장 | 업로드 중에는 spool/temp에 저장한다. 검증은 임시 extract/materialize 디렉터리에서 수행한다. RustFS에는 원본 archive를 저장하고 SHA-256, size, object key, etag를 DB에 기록한다. |
| 5 | 파일은 기본 삭제하지 않음. 삭제/다운로드는 admin UI에서 수동 | 기본 상태는 `available`. 삭제는 UI 명시 액션으로 `soft_deleted` 처리하고, 별도 confirm을 거친 hard delete만 RustFS object를 지운다. 다운로드 endpoint를 제공한다. |
| 6 | RustFS 직접 변경과 DB 정합성 검증/복구 | `ops.source_storage_reconcile_runs/items`를 추가한다. DB row만 있고 object가 없거나, object만 있고 DB row가 없거나, size/hash/etag가 다른 경우 UI에 노출하고 사용자가 직접 해결한다. |
| 7 | 기준년월이 다른 자료를 사용자가 직접 조합 | `ops.source_match_sets`와 `ops.source_match_set_items`를 추가한다. 정상 업로드된 파일만 match set에 넣을 수 있고, active DB/release가 어떤 match set을 쓰는지 UI에 표시한다. 모르면 `알수없음`으로 표시한다. |
| 8 | 업로드 상세 진행 상황과 실패 다이얼로그 | 업로드 byte progress는 반드시 퍼센트로 표시한다. 압축 검증, hash, RustFS 저장은 percent 가능 시 percent, 아니면 단계 label과 spinner를 표시한다. 실패 시 stage별 상세 로그 modal을 띄운다. |
| 9 | DB 구성 필수 자료뿐 아니라 검증용 자료도 업로드/매칭 optional 포함 | match set item은 `role='build_required'|'build_recommended'|'validation_optional'`을 가진다. optional 검증 자료가 없으면 `omitted=true`와 skip flag를 DB와 consistency report에 남긴다. 기존 DB에도 검증 자료를 나중에 붙여 validation job을 실행할 수 있다. |
| 10 | `건물군 내 상세주소 동 도형/*.zip`, `도로명주소 건물 도형/*.zip` 보강 | 기본 좌표 source에 바로 섞지 않고 optional validation/enrichment category로 등록한다. 후속 구현에서 staging table과 C11+ 검증 케이스로 사용한다. |
| 11 | 국가지점번호 도형/중심점 보강 | 10m 좌표 개선용이 아니라 parser/formatter/grid 검증과 coarse grid 보강 category로 둔다. optional 검증 자료로 match set에 포함한다. |
| 12 | 민원행정기관전자지도 활용 보강 | 주소 정본이 아니라 POI/기관 검증 category로 둔다. 기관 주소 geocode 결과와 SHP point 거리 비교 C15 후보로 설계한다. |
| 13 | incremental 업데이트 파일 업로드 제외 | 일변동 ZIP, `daily_juso_delta`, `juso_parcel_link_delta`, SHP delta 업로드는 T-109 범위에서 제외한다. UI category에도 노출하지 않는다. |

## 현재 카테고리 목록이 맞는지

사용자 요청 목록은 큰 방향이 맞다. 다만 현행 source kind와 원본 구조 기준으로 다음 보강이 필요하다.

| 사용자 표시명 | T-109 내부 category | 현행 source kind/job | 판정 | 보강/주의 |
|---------------|--------------------|----------------------|------|-----------|
| 위치정보요약DB | `locsum_full` | `locsum` / `locsum_load` | 필수 | 원본 `202604_위치정보요약DB_전체분.zip`, 내부 `entrc_*.txt` 17개를 기대한다. |
| 내비게이션용DB_전체분 | `navi_full` | `navi` / `navi_load` | 필수 | 원본이 `.7z`일 수 있다. 현 로더 입력에는 materialize가 필요하다. `match_build_*.txt`, `match_rs_entrc.txt`를 기대하고 `match_jibun_*.txt`는 검증 후보로 분리한다. |
| 도로명주소출입구_전체분 | `roadaddr_entrance_full` | `roadaddr_entrance` / `roadaddr_entrance_load` | 권장/조건부 | 실제 로컬 명칭은 `도로명주소 출입구 정보`. 현행에서는 optional이지만 `juso`와 기준월이 맞으면 좌표 품질 개선 효과가 커서 `serving_recommended` profile에 포함한다. |
| 구역의도형_전체분 | `zone_shape_full` | `sppn_makarea` / `sppn_makarea_load` | 권장/조건부 | 전체 ZIP을 받되 현행 사용 layer는 `TL_SPPN_MAKAREA`다. 중복 행정구역 layer는 재적재하지 않는다. |
| 도로명주소 한글_전체분 | `roadname_hangul_full` | `juso`, `parcel_link` / `juso_text_load`, `juso_parcel_link_load` | 필수 | 한 archive에서 `rnaddrkor_*.txt`와 `jibun_rnaddrkor_*.txt`를 모두 검증한다. 별도 `parcel_link` 업로드 slot을 만들지 않는다. |
| 도로명주소 전자지도 | `electronic_map_full` | `shp` / `shp_polygons_load` | 필수 | 시도별 ZIP 17개 묶음 또는 materialized 디렉터리를 받는다. serving 대상 9개 layer sidecar를 검증한다. |

따라서 T-109의 "DB 구성 기본 category"는 다음 6개로 둔다.

1. `roadname_hangul_full`
2. `locsum_full`
3. `navi_full`
4. `electronic_map_full`
5. `roadaddr_entrance_full`
6. `zone_shape_full`

하지만 load profile은 두 단계로 나눈다.

| profile | 필수 category | 의미 |
|---------|---------------|------|
| `serving_minimal` | `roadname_hangul_full`, `locsum_full`, `navi_full`, `electronic_map_full` | 현재 `SourceSetPlan.REQUIRED_SOURCE_KINDS`와 같은 최소 serving DB 구성. |
| `serving_recommended` | `serving_minimal` + `roadaddr_entrance_full`, `zone_shape_full` | 현 로컬 정확도 개선/국가지점번호 보조까지 포함한 권장 구성. 사용자가 omission을 명시할 수 있다. |

`roadaddr_entrance_full`과 `zone_shape_full`은 현행 코드에서는 optional이므로, 구현 PR에서 바로 hard-required로 바꾸면 기존 자동화와 충돌할 수 있다. UI에서는 `serving_recommended`를 기본 profile로 권장하되, 사용자가 `serving_minimal`을 선택하면 "출입구 보강/국가지점번호 보조 검증 생략" 플래그를 match set에 남긴다.

## 추가 보강/검증 category

정확도 개선 검토 결과를 반영해 다음 category를 명시적으로 추가한다. 이들은 기본 DB 구성에는 필수가 아니며, match set의 optional validation/enrichment 자료로 들어간다.

| category | 사용자 표시명 | 역할 | 현재 권장 |
|----------|---------------|------|-----------|
| `roadaddr_building_shape_bundle` | 도로명주소 건물 도형 | 출입구 point/connection line/주소 polygon 검증과 후보 scoring 보강 | optional validation 먼저. 바로 `mv_geocode_target`에 섞지 않음 |
| `detail_dong_shape_bundle` | 건물군 내 상세주소 동 도형 | 상세주소 동 polygon/동 출입구 검증, 상세주소 기능 후보 | optional validation. 일반 주소 좌표 후보로 쓰지 않음 |
| `detail_address_db_full` | 상세주소DB_전체분 | 상세주소 문자열/동 도형 key 검증 | optional validation. `detail_dong_shape_bundle`와 같이 쓰면 가치가 큼 |
| `national_point_grid_shape` | 국가지점번호 도형 | 100km/10km/1km/100m grid overlay와 parser 검증 | optional validation. 10m 좌표 개선용 아님 |
| `national_point_grid_center` | 국가지점번호 중심점 | 100m 이하 prefix 중심점 검증 | optional validation. 10m 좌표 개선용 아님 |
| `civil_service_institution_map` | 민원행정기관전자지도 | 행정기관 POI/주소 geocode 거리 검증 | optional validation/enrichment |
| `address_db_full` | 주소DB_전체분 | 도로명주소 한글 정본과 row/key drift 비교 | optional validation |
| `building_db_full` | 건물DB_전체분 | 건물 key/속성 drift, polygon/centroid coverage 검증 | optional validation |
| `navi_jibun_members` | 내비게이션용DB 지번 member | `match_jibun_*.txt` 기반 지번 link 검증 | 별도 upload가 아니라 `navi_full` archive 내부 optional member로 표시 |
| `epost_pobox_full` | epost 사서함 | 우편번호 보조 | 기존 optional 유지 |
| `epost_bulk_full` | epost 다량배달처 | 우편번호 보조 | 기존 optional 유지 |

## 범위에서 제외하는 것

다음은 T-109 범위에서 제외한다.

- 일변동 ZIP 업로드와 적용
- `daily_juso_delta`, `juso_parcel_link_delta`, `shp_polygons_delta`
- API가 자동으로 최신 파일을 다운로드하는 기능
- RustFS/PostgreSQL 생명주기 구동·정지·재시작
- 업로드한 archive를 자동 삭제하는 TTL 정책
- 새 원천을 즉시 serving MV에 섞는 좌표 ranking 변경

특히 incremental 업데이트 파일은 UI category, match set builder, storage reconciliation 어디에도 업로드 대상으로 노출하지 않는다. 추후 필요하면 별도 T-ID와 별도 위험 검토가 필요하다.

## 기존 시스템과 충돌하는 지점

### 1. 자동 탐지 중심 upload set과 명시 category 업로드의 충돌

현재 `UploadSetCreateRequest`는 `purpose='full_load_source_set'`와 `storage_kind`만 받는다. 파일마다 `guess_source_kind()`로 source kind를 추정한다. T-109에서는 사용자가 카테고리 slot을 먼저 고르고, 서버는 그 slot의 기대 구조만 검증해야 한다.

권장 migration:

1. 기존 `/v1/admin/uploads`는 호환 유지한다.
2. 새 API `/v1/admin/source-files/upload-sessions`를 추가한다.
3. 새 API는 `category`와 `user_yyyymm`을 필수로 받는다.
4. 기존 upload set manifest는 브라우저 upload progress와 temp 상태 추적용으로만 사용한다.
5. 정상 검증이 끝난 archive만 `ops.source_files`에 등록한다.

### 2. `source_kind`와 category는 1:1이 아니다

`roadname_hangul_full` 하나는 `juso`와 `parcel_link` 두 source kind를 만든다. `navi_full` 하나는 `navi_load`의 `match_build_*.txt`, `match_rs_entrc.txt`와 optional 검증 member `match_jibun_*.txt`를 함께 담는다. `zone_shape_full`은 archive에 여러 layer가 있지만 현재 사용 layer는 `TL_SPPN_MAKAREA`뿐이다.

따라서 DB category는 source kind보다 상위 개념으로 둔다.

```text
source file category  -> 하나 이상의 loader source kind/job
source kind           -> 기존 loader와 row-level source_yyyymm 추적 단위
match set item        -> 특정 category의 특정 업로드 파일을 특정 역할로 선택한 기록
```

### 3. `ops.artifacts`와 원천 파일 registry의 역할 분리

`ops.artifacts`는 백업 파일, 복원 로그, consistency export, 성능 리포트 같은 "산출물" registry다. 업로드 원천 archive는 DB 재구성의 입력이므로 `ops.artifacts`에 섞지 않고 `ops.source_files`로 별도 관리한다. 다만 source inventory export를 만들면 그 export 파일은 `ops.artifacts(artifact_type='source_inventory')`가 될 수 있다.

### 4. RustFS object는 사용자가 직접 변경할 수 있다

T-076은 RustFS upload set을 manifest로 관리하지만, 사용자가 RustFS console/S3 client로 object를 추가·삭제하면 manifest와 DB가 어긋난다. T-109에서는 DB registry와 RustFS prefix scan 결과를 비교하는 reconciliation을 공식 기능으로 둔다.

### 5. `C1~C10` 정합성 케이스가 고정 상수에 가깝다

현재 `core.consistency_definitions`와 UI는 C1~C10을 전제로 한다. optional 검증 자료가 늘어나면 C11 이상이 필요하다. 구현에서는 정적 tuple에 C11+를 추가할 수 있지만, 장기적으로는 DB/코드 registry에서 case metadata를 API로 내려 UI가 동적으로 탭을 그리게 해야 한다.

## 데이터 모델 제안

### `ops.source_files`

정상 업로드된 압축 원본 파일의 정본 registry다. 파일 하나는 한 category에 속한다. 같은 archive를 여러 match set에서 재사용할 수 있다.

```sql
CREATE TABLE ops.source_files (
  source_file_id        UUID PRIMARY KEY,
  category              TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  original_filename     TEXT NOT NULL,
  content_type          TEXT,
  compression_format    TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  user_yyyymm           TEXT NOT NULL CHECK (user_yyyymm ~ '^\d{6}$'),
  inferred_yyyymm       TEXT CHECK (inferred_yyyymm IS NULL OR inferred_yyyymm ~ '^\d{6}$'),
  inferred_yyyymm_basis TEXT,
  yyyymm_mismatch       BOOLEAN NOT NULL DEFAULT false,
  size_bytes            BIGINT NOT NULL CHECK (size_bytes >= 0),
  sha256                TEXT NOT NULL CHECK (length(sha256) = 64),
  duplicate_of_file_id  UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  storage_kind          TEXT NOT NULL,
  storage_uri           TEXT NOT NULL,
  bucket                TEXT,
  object_key            TEXT,
  object_etag           TEXT,
  object_version_id     TEXT,
  rustfs_endpoint_hash  TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

권장 state:

| state | 의미 |
|-------|------|
| `uploading` | byte upload 진행 중. DB row를 미리 만들 경우에만 사용 |
| `validating` | temp extract와 구조 검증 중 |
| `available` | 정상 검증 완료, match set에 사용 가능 |
| `quarantined` | 파일은 보존하지만 구조/정합성 문제가 있어 기본 선택 금지 |
| `missing` | DB row는 있으나 RustFS object가 없음 |
| `soft_deleted` | UI에서 삭제 처리했지만 감사 목적으로 row 보존 |
| `hard_deleted` | RustFS object까지 삭제된 상태. row는 감사 목적으로 남김 |

권장 index:

```sql
CREATE INDEX idx_ops_source_files_category_yyyymm
  ON ops.source_files (category, user_yyyymm, uploaded_at DESC)
  WHERE state = 'available';

CREATE INDEX idx_ops_source_files_sha256
  ON ops.source_files (sha256, size_bytes);

CREATE UNIQUE INDEX idx_ops_source_files_object_key
  ON ops.source_files (bucket, object_key)
  WHERE object_key IS NOT NULL AND state <> 'hard_deleted';
```

`sha256 + size_bytes`는 중복 탐지용이지 무조건 unique로 두지 않는다. 같은 파일을 다른 category로 잘못 올린 사례를 UI가 보여줘야 하므로 DB constraint보다 duplicate detection warning이 안전하다.

### `ops.source_file_members`

압축파일 내부 member/layer 검증 결과다. 시도별 ZIP 17개, SHP sidecar, TXT member, DBF field summary를 관리한다.

```sql
CREATE TABLE ops.source_file_members (
  member_id          UUID PRIMARY KEY,
  source_file_id     UUID NOT NULL REFERENCES ops.source_files(source_file_id) ON DELETE CASCADE,
  member_path        TEXT NOT NULL,
  member_kind        TEXT NOT NULL,
  sido_code          TEXT,
  sido_name          TEXT,
  layer_name         TEXT,
  geometry_type      TEXT,
  record_count       BIGINT,
  size_bytes         BIGINT,
  sha256             TEXT,
  dbf_fields         JSONB,
  detected_yyyymm    TEXT,
  validation_notes   JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

예시:

- `roadname_hangul_full`: `rnaddrkor_*.txt`, `jibun_rnaddrkor_*.txt` 각각 17개
- `locsum_full`: `entrc_*.txt` 17개
- `navi_full`: `match_build_*.txt` 17개, `match_rs_entrc.txt` 1개, `match_jibun_*.txt` 17개
- `electronic_map_full`: 시도별 ZIP 내부 9개 serving layer의 `.shp/.shx/.dbf`
- `roadaddr_entrance_full`: `RNENTDATA_*.txt` 17개
- `zone_shape_full`: `TL_SPPN_MAKAREA.{shp,shx,dbf}` 17개

### `ops.source_file_validations`

검증 실행 이력이다. 같은 파일도 validator 버전이 바뀌면 재검증할 수 있다.

```sql
CREATE TABLE ops.source_file_validations (
  validation_id       UUID PRIMARY KEY,
  source_file_id      UUID NOT NULL REFERENCES ops.source_files(source_file_id) ON DELETE CASCADE,
  validator_version   TEXT NOT NULL,
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  stage               TEXT,
  progress            DOUBLE PRECISION NOT NULL DEFAULT 0,
  error_code          TEXT,
  error_message       TEXT,
  log_tail            TEXT,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

### `ops.source_storage_reconcile_runs`

RustFS와 DB registry의 일관성 검증 실행 단위다.

```sql
CREATE TABLE ops.source_storage_reconcile_runs (
  reconcile_run_id    UUID PRIMARY KEY,
  prefix              TEXT NOT NULL,
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  scanned_objects     BIGINT NOT NULL DEFAULT 0,
  scanned_db_files    BIGINT NOT NULL DEFAULT 0,
  mismatch_count      BIGINT NOT NULL DEFAULT 0,
  resolved_count      BIGINT NOT NULL DEFAULT 0,
  log_tail            TEXT,
  summary             JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

### `ops.source_storage_reconcile_items`

개별 불일치 항목이다.

```sql
CREATE TABLE ops.source_storage_reconcile_items (
  reconcile_item_id   UUID PRIMARY KEY,
  reconcile_run_id    UUID NOT NULL REFERENCES ops.source_storage_reconcile_runs(reconcile_run_id) ON DELETE CASCADE,
  issue_type          TEXT NOT NULL,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  object_key          TEXT,
  db_sha256           TEXT,
  object_sha256       TEXT,
  db_size_bytes       BIGINT,
  object_size_bytes   BIGINT,
  db_etag             TEXT,
  object_etag         TEXT,
  severity            TEXT NOT NULL,
  state               TEXT NOT NULL DEFAULT 'open',
  resolution_action   TEXT,
  resolved_by         TEXT,
  resolved_at         TIMESTAMPTZ,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

권장 `issue_type`:

| issue_type | 의미 | UI 해결 액션 |
|------------|------|--------------|
| `db_missing_object` | DB에는 `available` 파일이 있는데 RustFS object가 없음 | DB row를 `missing`/`soft_deleted`로 바꾸거나, 같은 hash 파일을 재업로드해 재연결 |
| `object_missing_db` | RustFS object가 있는데 DB row가 없음 | category와 `user_yyyymm`을 입력해 DB registry에 import하거나, RustFS object 삭제 |
| `size_mismatch` | object size가 DB와 다름 | object 재다운로드/hash 확인 후 quarantine 또는 hash/size 재기록 |
| `hash_mismatch` | SHA-256이 다름 | 손상 가능성으로 기본 사용 금지. 사용자가 재해시 후 `update_hash_after_verify` 또는 삭제 |
| `etag_mismatch` | ETag만 다름 | multipart/metadata 차이 가능. size/hash가 같으면 정보성으로 resolve 가능 |
| `duplicate_object` | 같은 sha256/size object가 여러 key에 있음 | 하나를 유지하고 나머지는 soft delete 후보로 표시 |

`hash_mismatch`에서 "hash 일치화"는 단순히 DB 값을 object 값으로 덮어쓰는 버튼이 아니다. 서버가 object를 다시 읽어 SHA-256을 계산하고, 사용자가 "현재 object를 새 정본으로 인정"한다는 확인을 해야만 `ops.source_files.sha256`을 갱신한다. 그 전까지는 해당 파일을 match set에 사용할 수 없게 한다.

### `ops.source_match_sets`

DB 재구성 또는 검증 실행에 사용할 파일 조합의 상위 객체다.

```sql
CREATE TABLE ops.source_match_sets (
  source_match_set_id      UUID PRIMARY KEY,
  name                     TEXT NOT NULL,
  description              TEXT,
  profile                  TEXT NOT NULL,
  state                    TEXT NOT NULL,
  source_set_hash          TEXT NOT NULL,
  mixed_yyyymm             BOOLEAN NOT NULL DEFAULT false,
  yyyymm_by_category       JSONB NOT NULL DEFAULT '{}'::jsonb,
  omitted_optional         JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at             TIMESTAMPTZ,
  last_load_job_id         TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  last_consistency_report_id TEXT REFERENCES load_consistency_reports(report_id) ON DELETE SET NULL,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

권장 state:

| state | 의미 |
|-------|------|
| `draft` | 사용자가 조합 중 |
| `validated` | 모든 필수 파일과 선택 검증 skip flag가 확인됨 |
| `active` | 현재 serving release 또는 rebuild 작업의 기준 |
| `retired` | 더 이상 기본 선택하지 않음 |
| `invalid` | 참조 파일이 missing/quarantined가 되어 사용 불가 |

### `ops.source_match_set_items`

match set에 포함된 category별 파일 또는 생략 기록이다.

```sql
CREATE TABLE ops.source_match_set_items (
  source_match_set_item_id UUID PRIMARY KEY,
  source_match_set_id      UUID NOT NULL REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE CASCADE,
  category                 TEXT NOT NULL,
  role                     TEXT NOT NULL,
  source_file_id           UUID REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  required                 BOOLEAN NOT NULL DEFAULT false,
  omitted                  BOOLEAN NOT NULL DEFAULT false,
  omitted_reason           TEXT,
  user_yyyymm              TEXT,
  effective_yyyymm         TEXT,
  validation_enabled       BOOLEAN NOT NULL DEFAULT true,
  load_order               INTEGER,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (
    (omitted = false AND source_file_id IS NOT NULL)
    OR (omitted = true AND source_file_id IS NULL)
  )
);
```

role:

| role | 의미 |
|------|------|
| `build_required` | 해당 profile에서 DB 구성에 반드시 필요 |
| `build_recommended` | 없어도 load는 가능하지만 정확도/보조 기능이 낮아짐 |
| `validation_optional` | DB 구성에는 쓰지 않고 검증 또는 보강 분석에만 사용 |
| `enrichment_candidate` | 별도 staging 후 feature flag로 serving 보강 후보가 될 수 있음 |

## 카테고리별 기대 구조

### `roadname_hangul_full`

허용 입력:

- 단일 ZIP: `YYYYMM_도로명주소 한글_전체분.zip`
- 압축 해제 디렉터리

필수 내부 구조:

- `rnaddrkor_*.txt` 17개
- `jibun_rnaddrkor_*.txt` 17개

검증:

- `rnaddrkor`와 `jibun_rnaddrkor` 모두 존재해야 한다.
- 시도 코드/파일명 coverage가 17개인지 확인한다.
- 파일명에서 `YYYYMM`을 추론할 수 있으면 `inferred_yyyymm` 기본값으로 제안한다.
- 두 member group의 내부 기준월이 다르면 warning을 남긴다.

loader 매핑:

- `rnaddrkor_*.txt` → `juso_text_load`
- `jibun_rnaddrkor_*.txt` → `juso_parcel_link_load`

### `locsum_full`

허용 입력:

- `YYYYMM_위치정보요약DB_전체분.zip`
- 압축 해제 디렉터리

필수 내부 구조:

- `entrc_*.txt` 17개

검증:

- 좌표 컬럼 파싱 가능 여부를 sample로 확인한다.
- 좌표 결측 row count를 validation summary에 넣는다.
- `user_yyyymm`과 파일명 `YYYYMM`이 다르면 warning만 띄우고 저장은 허용하되 사용자가 명시 확인해야 한다.

loader 매핑:

- `locsum_load`

### `navi_full`

허용 입력:

- `YYYYMM_내비게이션용DB_전체분.7z`
- ZIP 또는 압축 해제 디렉터리

필수 내부 구조:

- `match_build_*.txt` 17개
- `match_rs_entrc.txt` 1개

optional 내부 구조:

- `match_jibun_*.txt` 17개

검증:

- 7z 해제 가능 여부를 확인한다.
- `match_build_*.txt`와 `match_rs_entrc.txt`가 없으면 실패한다.
- `match_jibun_*.txt`는 없으면 `navi_jibun_members.omitted=true`로 기록한다.
- 현 텍스트 로더가 직접 7z를 읽지 못하면 load 시 materialization 계획에 `extract_required=true`를 남긴다.

loader 매핑:

- `navi_load`
- `match_jibun_*.txt`는 T-109 1차 구현에서 loader 대상이 아니라 validation candidate다.

### `electronic_map_full`

허용 입력:

- 시도별 ZIP 17개를 한 category 업로드 세션에 업로드
- `도로명주소 전자지도/YYYYMM/<시도>.zip` 형태의 prefix import
- 압축 해제된 시도별 디렉터리

필수 layer:

- `TL_SCCO_CTPRVN`
- `TL_SCCO_SIG`
- `TL_SCCO_EMD`
- `TL_SCCO_LI`
- `TL_KODIS_BAS`
- `TL_SPRD_MANAGE`
- `TL_SPRD_INTRVL`
- `TL_SPRD_RW`
- `TL_SPBD_BULD`

각 layer는 최소 `.shp`, `.shx`, `.dbf` sidecar를 요구한다. `.prj`는 있으면 저장하고 없으면 EPSG:5179 기본 가정 여부를 validation summary에 남긴다.

검증:

- 시도별 ZIP 17개 coverage
- 내부 시도코드 디렉터리 존재
- 9개 layer sidecar 존재
- DBF header field presence
- geometry type이 기대값과 맞는지 sample 확인

loader 매핑:

- `shp_polygons_load(mode='full')`

### `roadaddr_entrance_full`

허용 입력:

- `도로명주소 출입구 정보/YYYYMM/<시도>.zip`
- `RNENTDATA_*.txt` 17개가 들어 있는 ZIP 또는 디렉터리

필수 내부 구조:

- `RNENTDATA_*.txt` 17개

검증:

- 내부 파일명 `RNENTDATA_2605_*`처럼 `YYMM` 기준월을 추론한다.
- 상위 디렉터리 기준월과 내부 파일 기준월이 다르면 내부 파일 기준월을 `inferred_yyyymm_basis='member_filename'`으로 우선 표시한다.
- `user_yyyymm`과 `roadname_hangul_full.user_yyyymm`이 다르면 same-month 좌표 승격이 되지 않을 수 있음을 match set builder에서 경고한다.

loader 매핑:

- `roadaddr_entrance_load`

### `zone_shape_full`

허용 입력:

- `구역의도형/YYYYMM/<시도>.zip`
- 압축 해제 디렉터리

필수 사용 layer:

- `TL_SPPN_MAKAREA.{shp,shx,dbf}`

무시 또는 중복 확인 layer:

- `TL_SCCO_CTPRVN`
- `TL_SCCO_SIG`
- `TL_SCCO_EMD`
- `TL_SCCO_LI`
- `TL_KODIS_BAS`
- `TL_SCCO_GEMD`

검증:

- `TL_SPPN_MAKAREA` 전국 coverage
- `SIG_CD + MAKAREA_ID` 중복 여부
- polygon validity sample
- 중복 행정구역 layer가 전자지도와 충돌하지 않도록 load 대상에서 제외한다는 summary

loader 매핑:

- `sppn_makarea_load(mode='full')`

### Optional validation category

| category | 필수 member/layer | 실패 시 |
|----------|-------------------|---------|
| `roadaddr_building_shape_bundle` | `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC` | 해당 category validation 실패. 기본 DB build는 계속 가능 |
| `detail_dong_shape_bundle` | `TL_SGCO_RNADR_DONG`, `TL_SPBD_ENTRC_DONG` | 상세주소 검증 skip 또는 실패 |
| `detail_address_db_full` | `adrdc_*.txt` 17개 | 상세주소 텍스트 검증 skip 또는 실패 |
| `national_point_grid_shape` | `TL_SPPN_GRID_100KM/10KM/1KM/100M` | 국가지점번호 grid 검증 skip 또는 실패 |
| `national_point_grid_center` | `SPPN_*.TXT` | 국가지점번호 중심점 검증 skip 또는 실패 |
| `civil_service_institution_map` | `민원행정기관_*.shp/.shx/.dbf/.prj` | POI/기관 검증 skip 또는 실패 |
| `address_db_full` | `주소_*.txt`, `부가정보_*.txt`, `지번_*.txt`, `개선_도로명코드_전체분.txt` | row/key drift 검증 skip 또는 실패 |
| `building_db_full` | `build_*.txt`, `jibun_*.txt`, `road_code_total.txt` | building key 검증 skip 또는 실패 |

## 업로드 상태 머신

한 파일 category upload session은 다음 state를 가진다.

```text
created
  -> uploading
  -> uploaded_to_temp
  -> extracting
  -> validating_structure
  -> hashing
  -> duplicate_check
  -> storing_to_rustfs
  -> verifying_rustfs_object
  -> registered
  -> available
```

실패 state:

```text
failed_upload
failed_extract
failed_structure
failed_hash
failed_rustfs_put
failed_rustfs_verify
cancelled
```

중요 원칙:

- `uploaded_to_temp` 이전 실패는 RustFS에 object를 만들지 않는다.
- `storing_to_rustfs` 중 실패하면 partial object를 삭제하거나 `*.part` key로 quarantine한다. 일반 prefix에 partial archive가 남으면 안 된다.
- `registered` 이후 실패는 DB row를 삭제하지 않고 `quarantined` 또는 `missing`으로 표시한다.
- 브라우저 업로드 progress는 byte 기반 percent 필수다.
- 서버 내부 검증 단계는 가능한 경우 `processed_bytes / total_bytes` percent를 제공한다. ZIP/7z member scan처럼 정확한 percent가 어려우면 spinner와 현재 stage text를 제공한다.

## RustFS 저장 규칙

원본 archive object key는 category와 기준년월을 포함한다.

```text
<prefix>/source-files/<category>/<user_yyyymm>/<source_file_id>/<original_filename>
```

예:

```text
kor-travel-geo/source-files/roadname_hangul_full/202605/3f.../202605_도로명주소 한글_전체분.zip
```

object metadata:

| metadata | 값 |
|----------|----|
| `x-amz-meta-ktg-source-file-id` | `source_file_id` |
| `x-amz-meta-ktg-category` | category |
| `x-amz-meta-ktg-user-yyyymm` | 사용자가 확정한 기준년월 |
| `x-amz-meta-ktg-sha256` | archive SHA-256 |
| `x-amz-meta-ktg-size-bytes` | archive size |

RustFS가 metadata를 안정적으로 보존하지 못하거나 S3 호환 차이가 있으면 DB 값을 우선한다. reconciliation은 object metadata가 없을 때도 object key, size, etag만으로 orphan 후보를 표시하고, 사용자가 category/기준년월을 입력해 import하도록 한다.

## API 설계

### Category 조회

```text
GET /v1/admin/source-file-categories
```

응답은 UI slot을 그리기 위한 정적 catalog다.

```json
{
  "categories": [
    {
      "category": "roadname_hangul_full",
      "label": "도로명주소 한글_전체분",
      "role": "build_required",
      "required_in_profiles": ["serving_minimal", "serving_recommended"],
      "accepted_extensions": [".zip"],
      "expected_members": ["rnaddrkor_*.txt", "jibun_rnaddrkor_*.txt"],
      "can_infer_yyyymm": true
    }
  ]
}
```

### 업로드 세션 생성

```text
POST /v1/admin/source-files/upload-sessions
```

요청:

```json
{
  "category": "roadname_hangul_full",
  "user_yyyymm": "202605",
  "display_name": "202605 도로명주소 한글 전체분",
  "storage_kind": "rustfs"
}
```

응답:

```json
{
  "upload_session_id": "source_upload_...",
  "category": "roadname_hangul_full",
  "user_yyyymm": "202605",
  "state": "created",
  "max_bytes": 2147483648
}
```

`user_yyyymm`은 필수다. UI가 파일명에서 `202605`를 추론했더라도 request에는 사용자가 확인한 값만 들어간다.

### 파일 업로드

```text
PUT /v1/admin/source-files/upload-sessions/{upload_session_id}/archive
```

raw body stream. 응답은 session status다.

브라우저는 `XMLHttpRequest.upload.onprogress` 또는 동등한 wrapper를 써서 byte percent를 표시한다. 서버도 `uploaded_bytes`, `total_bytes`를 기록하지만 브라우저 progress가 1차 표시 기준이다.

### 검증 시작/상태 조회

```text
POST /v1/admin/source-files/upload-sessions/{upload_session_id}/validate
GET  /v1/admin/source-files/upload-sessions/{upload_session_id}
GET  /v1/admin/source-files/upload-sessions/{upload_session_id}/events
```

검증은 upload 완료 후 별도 시작할 수 있게 한다. UI는 업로드 완료와 검증 실패를 분리해서 보여준다.

### RustFS 저장 및 registry 등록

```text
POST /v1/admin/source-files/upload-sessions/{upload_session_id}/commit
```

성공 응답:

```json
{
  "source_file_id": "uuid",
  "category": "roadname_hangul_full",
  "state": "available",
  "user_yyyymm": "202605",
  "sha256": "...",
  "size_bytes": 123,
  "storage_uri": "rustfs://..."
}
```

`commit`은 다음을 원자적으로 처리해야 한다.

1. archive SHA-256 계산 완료 확인
2. duplicate detection
3. RustFS put
4. RustFS head/get 검증
5. `ops.source_files` insert
6. `ops.source_file_members` insert
7. audit event 기록

완전한 DB transaction과 RustFS put은 분산 트랜잭션이 아니므로, 실패 복구 규칙이 필요하다. RustFS put 성공 후 DB insert 실패 시 reconciliation에서 `object_missing_db`로 잡히게 metadata를 object에 넣는다. DB insert 성공 후 object 확인 실패 시 `source_files.state='missing'` 또는 `quarantined`로 남긴다.

### 파일 목록/다운로드/삭제

```text
GET  /v1/admin/source-files?category=&yyyymm=&state=
GET  /v1/admin/source-files/{source_file_id}
GET  /v1/admin/source-files/{source_file_id}/download
POST /v1/admin/source-files/{source_file_id}/soft-delete
POST /v1/admin/source-files/{source_file_id}/hard-delete
POST /v1/admin/source-files/{source_file_id}/revalidate
```

삭제 원칙:

- 목록에서 row를 바로 삭제하지 않는다.
- `soft-delete`는 match set에서 새로 선택되지 않게 하되 감사 row와 RustFS object를 보존한다.
- `hard-delete`는 typed confirmation을 요구하고 RustFS object 삭제를 시도한다. 삭제 실패 시 DB row는 `quarantined` 또는 `delete_failed`로 남긴다.
- 이미 active release/match set이 참조하는 파일은 hard delete를 막고, 먼저 match set을 retire하도록 요구한다.

### RustFS 정합성 검증

```text
POST /v1/admin/source-files/reconcile
GET  /v1/admin/source-files/reconcile/{run_id}
GET  /v1/admin/source-files/reconcile/{run_id}/items
POST /v1/admin/source-files/reconcile/items/{item_id}/resolve
```

resolve action 예:

```json
{ "action": "mark_db_missing" }
{ "action": "soft_delete_db_row" }
{ "action": "import_object", "category": "locsum_full", "user_yyyymm": "202604" }
{ "action": "delete_object" }
{ "action": "update_hash_after_verify", "typed_confirmation": "현재 RustFS object를 정본으로 인정" }
```

## Match set API 설계

### 생성/수정

```text
POST /v1/admin/source-match-sets
PATCH /v1/admin/source-match-sets/{source_match_set_id}
POST /v1/admin/source-match-sets/{source_match_set_id}/items
DELETE /v1/admin/source-match-sets/{source_match_set_id}/items/{item_id}
POST /v1/admin/source-match-sets/{source_match_set_id}/validate
POST /v1/admin/source-match-sets/{source_match_set_id}/activate
POST /v1/admin/source-match-sets/{source_match_set_id}/retire
```

생성 요청 예:

```json
{
  "name": "202605 도로명주소 + 202604 전자지도 권장 조합",
  "profile": "serving_recommended",
  "items": [
    { "category": "roadname_hangul_full", "source_file_id": "...", "role": "build_required" },
    { "category": "locsum_full", "source_file_id": "...", "role": "build_required" },
    { "category": "navi_full", "source_file_id": "...", "role": "build_required" },
    { "category": "electronic_map_full", "source_file_id": "...", "role": "build_required" },
    { "category": "roadaddr_entrance_full", "source_file_id": "...", "role": "build_recommended" },
    { "category": "zone_shape_full", "source_file_id": "...", "role": "build_recommended" },
    { "category": "national_point_grid_center", "omitted": true, "omitted_reason": "미보유", "role": "validation_optional" }
  ]
}
```

검증 규칙:

- profile 필수 category가 빠지면 `validate` 실패.
- optional category는 `source_file_id` 또는 `omitted=true` 중 하나를 반드시 가져야 한다.
- 참조 파일이 `available`이 아니면 실패.
- `roadaddr_entrance_full.user_yyyymm`이 `roadname_hangul_full.user_yyyymm`과 다르면 "direct 출입구 좌표 승격 제한" warning.
- `zone_shape_full` 기준월이 다른 것은 허용하되 C10 note에 남긴다.
- 같은 category에 여러 파일을 넣으려면 category가 multi-file을 지원해야 한다. 기본은 category당 1개 registry file이다.

### DB 재구성

```text
POST /v1/admin/source-match-sets/{source_match_set_id}/rebuild-db
```

이 API는 기존 `full_load_batch`를 대체하지 않고, match set에서 `SourceSetPlan.batch_payload`를 생성해 기존 queue를 호출한다.

처리 흐름:

1. match set validate
2. 선택된 RustFS archive를 temp/materialized 작업 디렉터리로 다운로드
3. category별 압축 해제
4. 기존 loader가 기대하는 path로 materialize
5. `full_load_batch` children 생성
6. root payload에 `source_match_set_id`, category별 `source_file_id`, `user_yyyymm`, `sha256`, `storage_uri`를 남김
7. load 완료 후 consistency check와 MV refresh
8. `ops.dataset_snapshots.source_set`과 `ops.serving_releases`에 match set 연결

### 기존 DB에 검증 자료 추가 후 검증

```text
POST /v1/admin/source-match-sets/{source_match_set_id}/run-validation
```

이 API는 새 DB를 만들지 않고 optional validation category만 materialize해서 validation job을 실행한다.

요구사항:

- active release 또는 사용자가 고른 snapshot/match set 기준으로 실행한다.
- optional 자료가 없으면 `skipped=true`를 report에 남긴다.
- 새 케이스가 생기면 C11부터 번호를 붙이고 UI 탭에 표시한다.
- validation 결과는 `load_consistency_reports.source_set` 또는 별도 `validation_inputs`에 어떤 optional 자료가 있었고 무엇이 생략됐는지 기록한다.

## Admin UI 설계

### `/admin/source-files`

추천 신규 페이지다. 기존 `/admin/load`에 계속 모든 것을 넣으면 upload, match, rebuild, consistency가 한 화면에 과밀해진다.

탭:

| 탭 | 기능 |
|----|------|
| 파일 업로드 | category slot별 업로드, `user_yyyymm`, progress, 검증 결과 |
| 파일 목록 | category/기준년월/state/hash/storage 검색, 다운로드, revalidate, 삭제 |
| 매칭 세트 | DB 구성 파일과 optional 검증 파일 조합, validate, activate, rebuild |
| RustFS 정합성 | DB/RustFS 불일치 scan, issue 목록, 수동 resolve |
| 현재 구성 | active release가 참조하는 match set 표시. 없으면 `알수없음` |

### 카테고리별 업로드 카드

각 카드는 다음을 가진다.

- category label
- 이 category가 필요한 profile
- 기대 파일 설명
- `user_yyyymm` 입력
- 파일 선택/drop zone
- 추론 기준월 기본값 적용 버튼
- 업로드 progress bar
- 검증 stage timeline
- 실패 상세 로그 버튼
- 성공 후 `source_file_id`, hash, size, RustFS URI 요약

실수 방지:

- `roadname_hangul_full` 카드에 `위치정보요약DB` ZIP을 올리면 파일명/source 구조 검증에서 실패한다.
- generic "아무 파일이나 올리기"는 기본 UI에서 제거한다.
- 같은 브라우저 drag-and-drop으로 여러 category 파일을 한번에 뿌리는 기능은 1차 구현에서 금지한다. 사용자가 category별로 명시적으로 올리는 것이 목적이다.

### 기준년월 UX

규칙:

- `user_yyyymm` 입력은 필수다.
- 파일명이나 내부 member에서 `YYYYMM`/`YYMM`을 추론할 수 있으면 input 기본값으로 채운다.
- 추론 근거를 바로 표시한다. 예: `파일명 202605`, `내부 RNENTDATA_2605`, `상위 디렉터리 202604`.
- 추론값과 사용자가 입력한 값이 다르면 warning을 표시하되 저장을 막지는 않는다.
- match set builder에서는 category별 기준년월이 섞여 있음을 표로 보여준다.

### 진행률 UX

단계별 표시:

| 단계 | 표시 방식 |
|------|-----------|
| 브라우저 → API 업로드 | 필수 percent. `uploaded_bytes / total_bytes` |
| temp 저장 완료 | 완료 check |
| 압축 해제 | 가능하면 member 처리 수 percent, 아니면 spinner + 현재 member |
| 구조 검증 | validator rule count percent 또는 spinner |
| hash 생성 | 읽은 byte percent |
| 중복 확인 | spinner + 중복 후보 표시 |
| RustFS 저장 | 가능하면 put byte percent. 1차 구현에서 RustFS client가 percent를 못 주면 spinner + size 표시 |
| RustFS 검증 | head/get/hash 단계 label |
| DB registry 등록 | 완료 check |

실패 dialog:

- stage
- error code
- 사용자 메시지
- 기술 상세 로그
- 업로드 파일명/category/기준년월
- 재시도 가능 여부
- "이 파일을 quarantine으로 남기기" 또는 "세션 폐기" 선택

## 현재 구성 표시

admin UI 상단 또는 `/admin/source-files/current`에 다음을 표시한다.

| 항목 | 표시 |
|------|------|
| active serving release | release id, activated_at |
| active dataset snapshot | snapshot id, consistency severity |
| source match set | 이름, id, profile, state |
| category별 파일 | label, `user_yyyymm`, filename, hash 앞 12자, state |
| optional 검증 자료 | 포함/생략, 마지막 validation 결과 |

`ops.serving_releases` 또는 `ops.dataset_snapshots`에서 match set 연결을 찾을 수 없으면 다음처럼 표시한다.

```text
현재 DB를 만든 원천 매칭 정보: 알수없음
사유: 이 DB는 T-109 source match set 도입 전에 생성되었거나, 백업 복원 과정에서 match set metadata가 없습니다.
```

이 경우에도 기존 `load_manifest`, `load_jobs.payload.source_set`, `load_consistency_reports.source_set`에서 추정 가능한 정보는 "추정" 배지로 표시한다. 추정값은 match set 정본으로 저장하지 않는다.

## 검증 케이스 확장

현재 C1~C10은 유지한다. optional 자료를 활용하는 새 검증은 C11부터 추가한다.

제안:

| 코드 | 이름 | 입력 자료 | 생략 조건 |
|------|------|-----------|-----------|
| C11 | 출입구 원천 간 거리 검증 | `roadaddr_entrance_full`, `roadaddr_building_shape_bundle`, 전자지도 `TL_SPBD_ENTRC`, `locsum_full` | 건물 도형 bundle이 없으면 bundle 비교 skip |
| C12 | 건물 도형 bundle connection line 검증 | `roadaddr_building_shape_bundle`, 전자지도 도로 layer | bundle 없으면 skip |
| C13 | 상세주소 동 containment 검증 | `detail_dong_shape_bundle`, `detail_address_db_full`, 전자지도 `TL_SPBD_BULD` | 둘 중 하나 없으면 skip |
| C14 | 국가지점번호 grid/center 검증 | `national_point_grid_shape`, `national_point_grid_center`, `tl_sppn_makarea` | 둘 다 없으면 skip |
| C15 | 민원행정기관 POI 주소 거리 검증 | `civil_service_institution_map`, geocoder 결과 | 민원행정기관전자지도 없으면 skip |
| C16 | 주소DB/건물DB row/key drift 검증 | `address_db_full`, `building_db_full` | 해당 자료 없으면 skip |
| C17 | 내비 지번 member coverage 검증 | `navi_full` 내부 `match_jibun_*.txt`, `tl_juso_parcel_link` | member 없으면 skip |

각 consistency report에는 다음을 추가한다.

```json
{
  "validation_inputs": {
    "national_point_grid_center": {
      "state": "skipped",
      "reason": "match set item omitted",
      "source_file_id": null
    },
    "roadaddr_building_shape_bundle": {
      "state": "used",
      "source_file_id": "...",
      "sha256": "...",
      "user_yyyymm": "202604"
    }
  }
}
```

UI는 C1~C10을 특별 취급하지 않고 API가 내려주는 case definition 순서대로 탭을 그린다. 새 C11+가 들어와도 가로 스크롤 탭과 sample table이 깨지지 않아야 한다.

## 보강 자료 활용 원칙

### 도로명주소 건물 도형

직접 활용 가능성은 있지만 1차 구현에서는 검증용으로만 넣는다.

권장 단계:

1. `roadaddr_building_shape_bundle` 파일 registry/validation 구현
2. staging table 또는 streaming validator로 `TL_SPBD_ENTRC`와 기존 출입구 원천 비교
3. C11/C12 report 생성
4. 거리/coverage가 개선되는 케이스가 충분히 확인되면 별도 ADR로 대표 좌표 scoring 변경

금지:

- `TL_SGCO_RNADR_MST`를 `tl_spbd_buld_polygon`에 덮어쓰기
- `TL_SPBD_ENTRC`를 source priority 정의 없이 `mv_geocode_target`에 바로 union

### 건물군 내 상세주소 동 도형

일반 도로명주소 좌표 개선이 아니라 상세주소 기능과 검증용이다.

권장 단계:

1. `detail_dong_shape_bundle` 업로드/검증
2. `detail_address_db_full`과 match set optional pair 구성
3. C13 containment/key overlap 검증
4. 후속 상세주소 geocode feature에서 별도 endpoint 또는 `match_kind='detail'`로 사용

금지:

- 상세주소 동 polygon을 일반 주소 대표 polygon으로 대체
- 상세주소가 없는 일반 geocode 결과에 동/호 정보를 자동 부착

### 국가지점번호 도형/중심점

현 parser는 10m cell 중심을 계산한다. 도형/중심점 파일은 최대 100m 수준이므로 10m 정확도 개선 원천이 아니다.

권장:

- C14 parser/formatter regression
- 100m parent prefix 중심점 검증
- debug UI grid overlay
- `tl_sppn_makarea` 포함 여부와 grid coverage 분석

금지:

- 100m center를 10m 국가지점번호 좌표보다 정밀한 결과처럼 표시

### 민원행정기관전자지도

주소 정본이 아니라 POI 자료다.

권장:

- C15에서 `도로명주소` 문자열을 geocode한 결과와 SHP point 거리 비교
- 별도 `match_kind='place'` 또는 기관 검색 feature 후보
- 행정기관 위치 검증 sample export

금지:

- 기관명/기관 좌표를 일반 주소 후보에 섞어 vworld 호환 응답 구조를 깨기

## 백업/복원 manifest 확장

DB 백업 artifact manifest에는 기존 `source_set` 외에 T-109 정보를 추가한다.

```json
{
  "source_match_set": {
    "source_match_set_id": "...",
    "name": "202605 도로명주소 + 202604 전자지도 권장 조합",
    "profile": "serving_recommended",
    "source_set_hash": "...",
    "yyyymm_by_category": {
      "roadname_hangul_full": "202605",
      "locsum_full": "202604"
    },
    "items": [
      {
        "category": "roadname_hangul_full",
        "source_file_id": "...",
        "filename": "202605_도로명주소 한글_전체분.zip",
        "sha256": "...",
        "size_bytes": 123,
        "storage_uri": "rustfs://...",
        "role": "build_required"
      }
    ],
    "omitted_optional": {
      "national_point_grid_center": "사용자가 미보유로 생략"
    }
  }
}
```

복원 후에는 다음 순서로 검증한다.

1. backup manifest의 `source_match_set_id`가 현재 DB에 있는지 확인
2. 없으면 manifest 기반 read-only reconstructed match set을 `restored_from_backup` 상태로 생성할지 사용자에게 묻기
3. 각 `source_file_id`와 RustFS object 존재 여부 확인
4. object가 없으면 UI에 `db_missing_object` 또는 `source_file_unavailable` 표시
5. active release의 current source 구성을 표시. 정보가 부족하면 `알수없음`

## 구현 순서 제안

### 1단계: 문서/스키마/DTO

- category catalog 상수 추가
- `SourceFileCategory`, `SourceFile`, `SourceMatchSet` DTO 추가
- Alembic migration으로 `ops.source_*` 테이블 추가
- 기존 `UploadSetStatus`는 유지
- `docs/data-model.md`와 `docs/address-db-schema.md` 갱신

### 2단계: 백엔드 registry와 upload session

- category별 upload session API
- temp archive 저장
- archive hash/size 계산
- ZIP/7z/SHP 구조 validator
- RustFS put/head/hash verify
- DB registry insert
- file list/download/soft delete

### 3단계: RustFS reconciliation

- prefix scan
- DB row scan
- issue 생성
- resolve action
- audit event
- UI 목록

### 4단계: Match set builder

- match set CRUD
- profile required/recommended/optional validation
- omission flag
- active/current display
- 기존 `SourceSetPlan` 생성 bridge

### 5단계: validation 확장

- C11+ case definition 추가
- optional 자료 materialization
- skip flag와 `validation_inputs`
- UI dynamic case tab
- 기존 DB에 optional 자료를 붙여 validation job 실행

### 6단계: 보강 후보 실험

- 도로명주소 건물 도형 staging/streaming comparison
- 상세주소 동 도형 + 상세주소DB validation
- 국가지점번호 grid/center harness
- 민원행정기관전자지도 POI distance validation

## 테스트 계획

### 백엔드 단위 테스트

| 테스트 | 목적 |
|--------|------|
| category catalog validates required profiles | category 누락 방지 |
| upload session requires category and user_yyyymm | 기준년월 수동 입력 강제 |
| inferred yyyymm only pre-fills and mismatch warns | 자동 추정이 최종 판단이 아님 |
| wrong category archive fails structure validation | category별 명시 업로드 강제 |
| roadname hangul requires rnaddrkor and jibun_rnaddrkor | 한 archive가 두 source kind를 만드는 계약 고정 |
| navi 7z materialization marks extract_required | 7z 처리 계약 고정 |
| source file registry stores sha256/size/storage_uri | DB metadata 정본 |
| duplicate sha256 creates warning not hard error | 중복 탐지와 허용 분리 |
| soft delete blocks new match set selection | 삭제 정책 |
| hard delete blocks active match set reference | active 데이터 보호 |
| reconciliation detects db_missing_object | RustFS 직접 삭제 |
| reconciliation detects object_missing_db | RustFS 직접 추가 |
| reconciliation detects hash_mismatch | 손상 탐지 |
| match set requires build_required files | DB 구성 필수 자료 |
| match set records omitted optional validation | 검증 자료 생략 플래그 |
| rebuild bridge emits existing full_load_batch children | 기존 loader 재사용 |

### 프론트엔드 단위 테스트

| 테스트 | 목적 |
|--------|------|
| category cards render fixed slots | generic upload 회귀 방지 |
| yyyymm inferred value requires user confirmation | 기준월 UX |
| upload progress percent renders | 업로드 percent 필수 |
| validation spinner/stage renders | 비-percent 단계 표시 |
| failed stage opens detail dialog | 실패 상세 로그 |
| match set omitted optional appears as skipped | optional 검증 생략 표시 |
| current source config unknown fallback | `알수없음` 표시 |
| reconciliation issue actions render by issue_type | 정합성 복구 UI |
| C11+ tabs render dynamically | 새 검증 케이스 UI |

### 통합 테스트

처음에는 실제 전국 자료를 쓰지 않고 작은 fixture archive로 검증한다.

1. `roadname_hangul_full` fixture ZIP 업로드 → registry 등록
2. `locsum_full` fixture ZIP 업로드 → registry 등록
3. RustFS fake client로 object metadata 확인
4. object 삭제 simulation → reconciliation `db_missing_object`
5. RustFS orphan object simulation → reconciliation `object_missing_db`
6. match set 생성 → validation success
7. optional validation omitted → report skip flag

실제 자료 선택형 테스트는 `KTG_SLOW_REAL_DATA=1`일 때만 실행한다.

## 운영 주의점

- RustFS object는 기본 무기한 보존이므로 저장소 용량 모니터링이 필요하다.
- object 삭제는 UI에서 typed confirmation을 요구한다.
- DB registry가 있어도 RustFS object가 없으면 DB 재구성은 불가능하다.
- 백업 archive만으로는 원천 파일 RustFS object가 복원되지 않는다. 백업 manifest는 source file metadata를 담고, RustFS 원천 archive 보존은 별도 저장소 정책이다.
- `source_file_id`는 한 환경 안의 registry id다. 다른 환경으로 object를 옮기면 `sha256 + size + category + user_yyyymm`으로 import matching해야 한다.
- `user_yyyymm`은 사용자가 확정한 값이므로 파일명 추론과 달라도 감사 로그에 남긴다. 이를 조용히 자동 수정하지 않는다.
- optional 검증 자료가 없어서 skip된 케이스는 성공이 아니라 `skipped`다. UI와 report에서 명확히 구분한다.

## 후속 ADR 후보

구현 전에 다음 결정은 ADR로 고정하는 것이 좋다.

1. 원천 파일 registry는 `ops.source_files` 별도 테이블로 두고 `ops.artifacts`와 분리한다.
2. `roadaddr_entrance_full`과 `zone_shape_full`을 `serving_recommended` 기본값으로 두되, `serving_minimal`에서는 생략 가능하게 한다.
3. optional 검증 자료 생략은 match set item의 `omitted=true`와 consistency report `validation_inputs.skipped`로 기록한다.
4. RustFS hash mismatch 해결은 서버 재해시 후 사용자 typed confirmation이 있을 때만 DB hash 갱신을 허용한다.
5. incremental update upload는 T-109 범위에서 제외한다.
