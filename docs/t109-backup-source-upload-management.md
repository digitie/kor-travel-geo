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
  - `docs/architecture/data-model.md`
  - `docs/decisions.md` ADR-049
- 관련 기존 코드:
  - `src/kortravelgeo/dto/admin.py`
  - `src/kortravelgeo/infra/source_set.py`
  - `src/kortravelgeo/infra/uploads.py`
  - `src/kortravelgeo/infra/rustfs.py`
  - `src/kortravelgeo/loaders/juso_map.py`
  - `src/kortravelgeo/loaders/building_shape_bundle.py`
  - `src/kortravelgeo/loaders/extra_shape_layers.py`
  - `src/kortravelgeo/core/consistency_definitions.py`
  - `src/kortravelgeo/api/routers/admin.py`
  - `kor-travel-geo-ui/components/admin/LoadConsole.tsx`

## 한 줄 결론

기존 T-045/T-076의 upload set은 "파일을 받아 source kind를 추정한 뒤 적재 계획을 만든다"에 가깝다. T-109에서는 이 흐름을 **카테고리별 명시 업로드, 사용자가 확정한 기준년월, DB에 저장되는 원천 파일 registry, RustFS object 정합성 검증, 사용자가 조합하는 source match set, optional 검증 자료** 중심으로 재설계한다. 업로드 파일 자체는 압축파일 원본을 RustFS에 장기 보관하고, DB는 "무엇이 정상 업로드되어 어떤 match set에 쓰였는지"의 정본이 된다.

## PR #131 리뷰 반영 원칙과 확정 설계 결정

PR #131 상세 리뷰의 M1~M12, L1~L11을 구현 전에 모두 설계에 반영한다. M1은 사용자 결정에 따라 **전자지도 구조 검증을 11개 layer 필수**로 고정한다. 즉, `TL_SPBD_EQB`와 `TL_SPBD_ENTRC`는 "옵셔널"이 아니라 archive 정상성 검증에 반드시 필요한 layer다. 다만 현행 serving load 대상은 계속 9개 layer이며, `TL_SPBD_EQB`/`TL_SPBD_ENTRC`는 구조 검증과 후속 검증/보강 후보로 보존한다.

2026-06-14 추가 리뷰에서 시도별 ZIP 제공 방식도 확정됐다. `electronic_map_full`, `roadaddr_entrance_full`, `zone_shape_full`은 하나로 묶은 archive를 업로드하지 않고 **`<기준월>/<시도>.zip` 17개를 시도별 개별 파일로 업로드**한다. 따라서 단일 파일 크기 2GiB 한계는 현재 원천 기준으로 직접 blocker가 아니며, 설계의 핵심은 "시도별 파일 17개를 한 category group으로 묶어 match set에서 참조하는 방법"이다.

2026-06-14 사용자 결정으로 다음 선택지는 모두 확정한다. 아직 서비스 단계가 아니므로 호환성·최소 수정 비용보다 **확장성, 완성도, 일관성, 성능**을 우선한다. 단, admin/API/CLI/DTO처럼 외부에서 호출할 수 있는 인터페이스는 breaking change를 숨기지 않고 문서, OpenAPI, changelog, migration guide에 명확히 적는다.

| 항목 | 확정 결정 | 구현 지시 |
|------|-----------|-----------|
| C11+ case metadata | DB registry 기반 동적 case catalog | `CASE_DEFINITIONS` 정적 tuple은 초기 seed나 fallback 근거로만 두고, UI/API는 DB case registry를 정본으로 읽는다. |
| match set과 release/snapshot 연결 | `ops.dataset_snapshots.source_match_set_id` FK 추가 | active release는 snapshot을 통해 match set을 찾는다. `source_set` JSONB는 legacy/read-only fallback으로만 사용한다. |
| source file 검증 상태 | `state`와 `validation_state` 분리 | 보관 상태와 검증 상태를 별도 column으로 두고 CHECK/trigger로 모순 상태를 막는다. |
| commit 비원자성 처리 | storage-first 후 사용자 승인 기반 DB registry insert | 업로드 세션 생성 시 사용자가 `user_yyyymm`을 반드시 직접 입력·확정한다. UI는 파일명/내부 member에서 추정한 값 또는 현재 날짜 기준 `YYYYMM`을 입력 필드의 사전 입력값으로만 제안한다. RustFS 저장과 구조 검증을 먼저 끝낸 뒤 사용자가 세션의 기준년월, mismatch 경고, 검증 결과를 확인하고 "registry 등록"을 직접 승인한다. DB insert 실패는 저장된 object metadata와 upload session으로 재시도 가능하므로 오류가 아니라 복구 가능한 미등록 상태다. |
| admin 권한 모델 | admin role gate 도입 | read-only viewer, source-file manager, rebuild operator, destructive admin 같은 권한을 API와 UI에 강제한다. typed confirmation은 role gate를 대체하지 않고 보조 안전장치로만 쓴다. |
| PK 네이밍 | full-prefix ID로 통일 | T-109 신규 테이블은 `source_file_id` 같은 full-prefix를 사용한다. 기존 `ops` 테이블도 구현 단계에서 `dataset_snapshot_id`, `serving_release_id`, `audit_event_id`처럼 full-prefix로 rename하는 migration/API 변경을 포함한다. |
| 시도별 다중 파일 category 모델 | `ops.source_file_groups` 신설 | match set은 group을 참조하고, 시도별 ZIP 17개는 child `ops.source_files` 17행으로 보존한다. |
| 업로드 전략 | multipart/resumable upload | 1차 구현부터 multipart/resumable을 정식 경로로 둔다. 단일 PUT은 테스트 fixture 또는 내부 fallback으로만 제한한다. |
| RustFS hash 검증 | quick/deep reconciliation | 정기 scan은 size/etag가 직전 검증과 같으면 본문 재해시를 생략하고, 변경 감지 object 또는 사용자가 실행한 deep scan은 object 전체를 streaming 재해시해 mismatch를 즉시 확정한다. |

### PR #131 finding 반영 위치

| finding | 문서 반영 |
|---------|-----------|
| M1 | `electronic_map_full` 구조 검증을 11개 layer 필수로 고정하고 serving load 9개 layer와 분리 |
| M2 | C11+ 추가 전 `ops.consistency_case_samples.case_code` CHECK 완화 migration을 필수 단계로 추가 |
| M3 | `ops.dataset_snapshots.source_match_set_id` FK를 정본으로 명시 |
| M4 | `RustfsClient`의 `head_object`, `delete_object`, metadata 포함 `put_file`, multipart upload, 조건부 deep rehash helper 필요를 구현 범위에 추가 |
| M5 | `building_shape_bundle.py`, `extra_shape_layers.py`와 기존 비교 script 재사용을 보강 자료 단계에 명시 |
| M6 | `state`/`validation_state` 선택지, enum, 모순 방지 CHECK/trigger 필요를 명시 |
| M7 | upload session state와 registry state 매핑표를 추가 |
| M8 | DB/RustFS 비원자성, advisory lock, active match set partial unique, 미등록 stored object 복구 규칙을 추가 |
| M9 | destructive admin action의 typed confirmation, 감사 actor, role gate 선택지를 추가 |
| M10 | `effective_yyyymm`, `yyyymm_by_category`, `mixed_yyyymm` 산출 규칙을 추가 |
| M11 | PK 네이밍 선택지와 잘못된 심볼 경로 표기를 정정 |
| M12 | `source_file_groups`와 `multi_part` 모델을 추가하고 match set 참조 단위를 group으로 변경 |
| L1 | SHP 3종은 시도별 개별 ZIP 업로드로 확정해 2GiB 장애 요인을 해소하되, 업로드 경로는 1차 구현부터 multipart/resumable로 고정 |
| L2 | `TL_SPRD_INTRVL`은 DBF-only 검증 profile로 분리 |
| L3 | role 집합을 `build_required`, `build_recommended`, `validation_optional`, `enrichment_candidate` 4종으로 고정 |
| L4 | category catalog의 role은 기본값이고 최종 권위는 match set item role임을 명시 |
| L5 | `source_set_hash` 64자 CHECK와 canonical hash 산출 규칙을 명시 |
| L6 | FK `RESTRICT`가 아니라 group/file state guard와 audit event로 삭제 보호한다고 명시 |
| L7 | `navi_jibun_members`를 독립 category가 아닌 `navi_full` 내부 optional member flag로 변경 |
| L8 | upload SSE event schema, terminal state, polling fallback을 추가 |
| L9 | category당 단일 참조는 file이 아니라 group 단위 `UNIQUE (source_match_set_id, category)`로 정리 |
| L10 | epost `pobox`/`bulk` source kind와 `roadname_hangul_full`의 `juso`/`parcel_link` 전개를 명시 |
| L11 | `CASE_DEFINITIONS`, `REQUIRED_SOURCE_KINDS`, `build_full_load_source_set_plan`, `/v1/admin` 표기를 정정 |

### PR #131 추가 리뷰 반영 위치

head `3e223a4` 기준 추가 리뷰의 H/M/L 항목은 다음처럼 문서에 반영한다.

| finding | 반영 위치 |
|---------|-----------|
| H1 | 1단계 구현 순서와 테스트 계획에 `infra/sql.py` `SCHEMA_SQL`/`INDEX_SQL`, `sql/ddl/001_schema.sql`, Alembic 동시 갱신과 fresh init-db drift 테스트 추가 |
| H2 | `ops.consistency_case_definitions`를 기존 `ConsistencyCaseDefinition` DTO와 seed 가능한 컬럼으로 재정렬하고 `ops.consistency_case_inputs` link table 추가 |
| H3 | `Admin 권한 모델` 절에 trusted proxy header 기반 `RequestContext`, `require_role`, audit actor/role 규칙 추가 |
| H4 | DB 재구성 흐름에 download/materialize 병렬·파이프라인과 DB COPY 직렬 유지 규칙 추가 |
| H5 | snapshot 연결을 `ops.dataset_snapshots.source_match_set_id` FK 정본으로 고정하고 `source_set` JSONB와 `serving_releases` 직접 연결 표현 제거 |
| M1 | `recompute_group_aggregates(source_file_group_id)` 단일 service와 호출 지점 명시 |
| M2 | reconciliation `quick`/`deep` mode, `last_verified_*`, 조건부 재해시, deep cursor 추가 |
| M3 | register 단계에서 upload streaming SHA-256 재사용, `group_sha256` metadata 기반 계산, 불필요한 본문 재읽기 금지 |
| M4 | `user_yyyymm`을 group 단일 정본으로 축소하고 child/item 중복 저장 제거 |
| M5 | `source_set_hash`를 draft에서는 NULL 허용, validated 이상에서만 64자 필수로 변경 |
| M6 | `ops.source_upload_sessions`/`ops.source_upload_session_parts`와 `orphaned_multipart` reconciliation 추가 |
| M7 | reconciliation item, object key, part 기반 dedup, incomplete group index 추가 |
| L1 | 시도별 고정 모델을 `multi_part` + `part_kind`/`part_key` 모델로 일반화 |
| L2 | RustFS object key를 `<category>/<user_yyyymm>/<group>/<file>/<part_key>` prefix로 변경 |
| L3/L4 | source registry FK는 `RESTRICT`, snapshot match set FK는 `SET NULL` + app guard로 정리 |
| L5 | case 입력 category를 `ops.consistency_case_inputs` link table로 검증 |
| L6 | 신규 CHECK는 `char_length()`와 명시 constraint 이름을 사용 |
| L7 | SHP/DBF header 검증은 필요한 byte만 부분 read하도록 명시 |
| L8 | multi-part 부분 재업로드 lifecycle과 미등록 object import 단계화 추가 |
| 잔여 finding | `rebuild-db`와 `run-validation`에 RustFS materialize 직후/loader 사용 직전 무결성 게이트를 추가하고, 아래 "운영 시나리오 커버리지 점검" 표로 누락 분기를 검산 |
| 시나리오 누락 집중 리뷰 | 진행 중 upload session 재개 진입점, rebuild 중단 복구, consistency ERROR 승격 gate, match set `integrity_alert`/`invalid` 복구, 복원 후 `restored_from_backup` stub 생성, 미등록 stored object의 `pending_registration` 분리를 추가 |
| 시나리오 재검 잔여 M/L | active match set 무결성 결손은 `integrity_alert`로 분리하고, `soft_deleted` restore, restore hot-swap 후 source quick reconcile, session 만료/janitor, restore stub 검증 순서, 중복 session 409, register 전 slot 교체, validator version 전파, forced promotion 범위를 추가 |

## 요구사항 반영 매트릭스

| 번호 | 요구사항 | 설계 반영 |
|------|----------|-----------|
| 1 | 파일 업로드를 파일 카테고리별로 명시적으로 분리 | `/admin/source-files`의 새 source registry 영역에서 카테고리 slot별 업로드만 허용한다. **자동 source kind 추정(`guess_source_kind`)은 제거**하고, source kind는 사용자가 고른 category에서 결정론적으로 전개한다(충돌 지점 #1). |
| 2 | 기준년월은 사용자가 직접 입력, 파일명 추정은 UI 기본값만 | 모든 업로드는 `user_yyyymm` 필수. `inferred_yyyymm`은 기본값과 경고 표시용으로만 사용하고, 추정 불가 시 현재 날짜 기준 `YYYYMM`을 기본값으로 제안한다. 최종 저장과 match set은 사용자가 제출한 `user_yyyymm`을 사용한다. |
| 3 | 업로드 파일 정보 DB 관리 | `ops.source_files`, `ops.source_file_members`, `ops.source_file_validations`를 추가한다. 기존 `upload-set.json`은 작업 캐시로 남기되 정본이 아니다. |
| 4 | 임시 디렉터리 저장 → 압축 해제/구조 검증 → 압축파일 원본을 RustFS 저장 | 업로드 중에는 spool/temp에 저장한다. 검증은 임시 extract/materialize 디렉터리에서 수행한다. RustFS에는 원본 archive를 저장하고 SHA-256, size, object key, etag를 DB에 기록한다. |
| 5 | 파일은 기본 삭제하지 않음. 삭제/다운로드는 admin UI에서 수동 | 기본 상태는 `available`. 삭제는 UI 명시 액션으로 `soft_deleted` 처리하고, 별도 confirm을 거친 hard delete만 RustFS object를 지운다. 다운로드 endpoint를 제공한다. |
| 6 | RustFS 직접 변경과 DB 정합성 검증/복구 | `ops.source_storage_reconcile_runs/items`를 추가한다. DB row만 있고 object가 없거나, object만 있고 DB row가 없거나, size/hash/etag가 다른 경우 UI에 노출하고 사용자가 직접 해결한다. |
| 7 | 기준년월이 다른 자료를 사용자가 직접 조합 | `ops.source_match_sets`와 `ops.source_match_set_items`를 추가한다. 정상 업로드된 파일만 match set에 넣을 수 있고, active DB/release가 어떤 match set을 쓰는지 UI에 표시한다. 모르면 `알수없음`으로 표시한다. |
| 8 | 업로드 상세 진행 상황과 실패 다이얼로그 | 업로드 byte progress는 반드시 퍼센트로 표시한다. 압축 검증, hash, RustFS 저장은 percent 가능 시 percent, 아니면 단계 label과 spinner를 표시한다. 실패 시 stage별 상세 로그 modal을 띄운다. |
| 9 | DB 구성 필수 자료뿐 아니라 검증용 자료도 업로드/매칭 optional 포함 | match set item은 `role='build_required'|'build_recommended'|'validation_optional'|'enrichment_candidate'`를 가진다. optional 검증 자료가 없으면 `omitted=true`와 skip flag를 DB와 consistency report에 남긴다. 기존 DB에도 검증 자료를 나중에 붙여 validation job을 실행할 수 있다. |
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
| 도로명주소출입구_전체분 | `roadaddr_entrance_full` | `roadaddr_entrance` / `roadaddr_entrance_load` | 권장/조건부 | 실제 로컬 명칭은 `도로명주소 출입구 정보`. `<기준월>/<시도>.zip` 17개를 시도별 개별 파일로 업로드해 하나의 group으로 묶는다. 현행에서는 optional이지만 `juso`와 기준월이 맞으면 좌표 품질 개선 효과가 커서 `serving_recommended` profile에 포함한다. |
| 구역의도형_전체분 | `zone_shape_full` | `sppn_makarea` / `sppn_makarea_load` | 권장/조건부 | `<기준월>/<시도>.zip` 17개를 시도별 개별 파일로 업로드해 하나의 group으로 묶는다. 현행 사용 layer는 `TL_SPPN_MAKAREA`다. 중복 행정구역 layer는 재적재하지 않는다. |
| 도로명주소 한글_전체분 | `roadname_hangul_full` | `juso`, `parcel_link` / `juso_text_load`, `juso_parcel_link_load` | 필수 | 한 archive에서 `rnaddrkor_*.txt`와 `jibun_rnaddrkor_*.txt`를 모두 검증한다. 별도 `parcel_link` 업로드 slot을 만들지 않는다. |
| 도로명주소 전자지도 | `electronic_map_full` | `shp` / `shp_polygons_load` | 필수 | `<기준월>/<시도>.zip` 17개를 시도별 개별 파일로 업로드해 하나의 group으로 묶는다. 현행 discovery와 맞춰 각 시도 ZIP마다 11개 layer sidecar를 모두 필수로 검증하고, 그중 9개 layer만 현 serving load 대상으로 사용한다. |

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
| `serving_minimal` | `roadname_hangul_full`, `locsum_full`, `navi_full`, `electronic_map_full` | 현재 `kortravelgeo.infra.source_set.REQUIRED_SOURCE_KINDS`와 같은 최소 serving DB 구성. 단, `roadname_hangul_full` 하나가 `juso`와 `parcel_link` 두 source kind로 전개되므로 category는 4개지만 loader source kind는 5개다. |
| `serving_recommended` | `serving_minimal` + `roadaddr_entrance_full`, `zone_shape_full` | 현 로컬 정확도 개선/국가지점번호 보조까지 포함한 권장 구성. 사용자가 omission을 명시할 수 있다. |

`roadaddr_entrance_full`과 `zone_shape_full`은 현행 코드에서는 optional이므로, 구현 PR에서 바로 hard-required로 바꾸면 기존 자동화와 충돌할 수 있다. UI에서는 `serving_recommended`를 기본 profile로 권장하되, 사용자가 `serving_minimal`을 선택하면 "출입구 보강/국가지점번호 보조 검증 생략" 플래그를 match set에 남긴다.

## 추가 보강/검증 category

정확도 개선 검토 결과를 반영해 다음 category를 명시적으로 추가한다. 이들은 기본 DB 구성에는 필수가 아니며, match set의 optional validation/enrichment 자료로 들어간다.

category는 파일 개수 관점에서 두 종류다.

| group_kind | 의미 | 해당 category |
|------------|------|---------------|
| `single_file` | 하나의 archive가 하나의 registry group을 이룸 | `roadname_hangul_full`, `locsum_full`, `navi_full`, `detail_address_db_full`, `national_point_grid_shape`, `national_point_grid_center`, `civil_service_institution_map`, `address_db_full`, `building_db_full`, `epost_pobox_full`, `epost_bulk_full` |
| `multi_part` + `part_kind='sido'` | 시도별 개별 ZIP 17개가 하나의 registry group을 이룸 | `electronic_map_full`, `roadaddr_entrance_full`, `zone_shape_full`, `roadaddr_building_shape_bundle`, `detail_dong_shape_bundle` |

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
| `navi_full.match_jibun` | 내비게이션용DB 지번 member | `match_jibun_*.txt` 기반 지번 link 검증 | 독립 category가 아니라 `navi_full` archive의 optional member flag로 관리 |
| `epost_pobox_full` | epost 사서함 | 우편번호 보조 (별도 수동 적재) | 사용자 트리거 server-fetch → RustFS → `pobox_load`로 DB 반영·검증. `source_match_set` 핵심 rebuild에는 넣지 않음. 아래 "epost 우편번호 자료" 절 |
| `epost_bulk_full` | epost 다량배달처 | 우편번호 보조 (별도 수동 적재) | 사용자 트리거 server-fetch → RustFS → `bulk_load`로 DB 반영·검증. `source_match_set` 핵심 rebuild에는 넣지 않음. 아래 "epost 우편번호 자료" 절 |

### epost 우편번호 자료 (수동 server-fetch)

`epost_pobox_full`(사서함)·`epost_bulk_full`(다량배달처)은 우편번호 보조 자료다. 핵심 serving DB(`mv_geocode_target`)를 만드는 `source_match_set` 구성·rebuild에는 포함하지 않는다(`kortravelgeo.infra.source_set.REQUIRED_SOURCE_KINDS`에도 없음). 대신 다음 **별도 수동 흐름**으로 적재·검증한다(2026-06-14 결정).

1. 운영자가 `/admin/source-files`에서 "epost 받기"를 명시적으로 클릭한다(사용자 트리거 전용. 자동·스케줄·polling 다운로드는 두지 않는다).
2. 서버가 운영 설정에 등록된 epost fetch source(자료 URL 등)에서 pobox/bulk 자료를 다운로드한다. 진행률·실패는 업로드 세션과 동일한 SSE/상태로 노출하고, 실패 시 재시도·취소를 제공한다. fetch source와 자격증명은 운영 설정으로 두고 문서에 값으로 남기지 않는다.
3. 받은 파일을 다른 category와 동일하게 RustFS에 저장하고 `ops.source_file_groups`/`ops.source_files`에 `single_file`로 register한다(SHA-256/size 기록, reconciliation·정합성 검증 대상 포함). 즉 취득 방식만 server-fetch이고, 그 뒤 registry/RustFS/reconciliation 규칙은 업로드 자료와 동일하다.
4. register 후 기존 `pobox_load`/`bulk_load` job으로 DB에 반영한다. 이 적재는 `full_load_batch` 핵심 rebuild와 **독립적으로** 실행할 수 있다(우편번호는 별도 테이블이라 serving MV swap과 무관).
5. 적재 후 우편번호 검증(row count, 필수 컬럼 presence, 우편번호 형식·중복 sanity 등)을 수행해 report에 남긴다. 검증 실패는 적재 결과와 함께 노출하고, 우편번호 조회 활성 반영 여부는 운영자가 결정한다.

이 server-fetch는 "API가 자동으로 최신 파일을 다운로드하는 기능"(아래 범위 제외)의 **명시적 예외**다. 차이는 항상 사용자 클릭으로만 트리거되고 스케줄·자동 polling이 없다는 점이다.

## 범위에서 제외하는 것

다음은 T-109 범위에서 제외한다.

- 일변동 ZIP 업로드와 적용
- `daily_juso_delta`, `juso_parcel_link_delta`, `shp_polygons_delta`
- API가 자동/스케줄/polling으로 최신 파일을 다운로드하는 기능 (단, epost 우편번호 자료는 사용자가 명시 클릭으로 트리거하는 **수동 server-fetch**를 예외로 허용한다 — 위 "epost 우편번호 자료" 절. 자동·주기 다운로드는 제외 유지)
- RustFS/PostgreSQL 생명주기 구동·정지·재시작
- 업로드한 archive를 자동 삭제하는 TTL 정책
- 새 원천을 즉시 serving MV에 섞는 좌표 ranking 변경

특히 incremental 업데이트 파일은 UI category, match set builder, storage reconciliation 어디에도 업로드 대상으로 노출하지 않는다. 추후 필요하면 별도 T-ID와 별도 위험 검토가 필요하다.

## 기존 시스템과 충돌하는 지점

### 1. 자동 탐지(`guess_source_kind`) 제거와 명시 category 업로드 단일화

현재 `UploadSetCreateRequest`는 `purpose='full_load_source_set'`와 `storage_kind`만 받고, 파일마다 `guess_source_kind()`로 source kind를 추정한다(`infra/source_set.py`의 `guess_source_kind`/`build_full_load_source_set_plan`, `infra/uploads.py`의 source_kind 자동 채움 4곳). 이 자동 추정은 "카테고리별 명시 업로드"와 정면 충돌한다. **T-109에서는 자동 탐지 기능 자체를 제거한다(2026-06-14 결정).** 아직 서비스 전이므로 호환 alias를 쌓지 않고 source kind 추정 경로를 정리한다.

확정 migration:

1. `guess_source_kind()`와 그 호출부(`infra/source_set.py`, `infra/uploads.py`의 source_kind 자동 채움)를 **제거**한다. source kind는 추정하지 않고, 사용자가 고른 category에서 "카테고리별 기대 구조" 매핑 표(category → loader source kind/job)로 **결정론적으로 전개**한다.
2. 자동 탐지에 의존하던 기존 `/v1/admin/uploads` upload set 흐름은 폐기하고, 업로드는 `/v1/admin/source-files/upload-sessions`(`category`·`user_yyyymm` 필수)로 단일화한다. 이는 admin API breaking change이므로 OpenAPI·DTO·TypeScript type·CLI·changelog·migration guide에 명시한다.
3. 서버는 사용자가 고른 category slot의 기대 구조만 검증한다. 추정값은 저장·표시·match set 어디에도 쓰지 않는다.
4. 정상 검증이 끝난 archive만 `ops.source_files`에 등록한다.

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

현재 `kortravelgeo.core.consistency_definitions.CASE_DEFINITIONS` 정적 tuple과 UI는 C1~C10을 전제로 한다. optional 검증 자료가 늘어나면 C11 이상이 필요하므로, T-109에서는 case metadata의 정본을 DB registry로 옮긴다. `CASE_DEFINITIONS`는 초기 seed, migration 검증, 또는 DB registry가 비어 있는 개발 fixture용 fallback 근거로만 사용한다. UI는 case registry API가 내려주는 정의를 기준으로 탭과 sample table을 그린다. `ops.consistency_case_samples.case_code` CHECK는 현재 C1~C10만 허용하므로 `^C\d+$` 같은 패턴으로 완화하는 Alembic migration을 반드시 포함한다.

## 데이터 모델 제안

### 기존 `ops` ID 네이밍 정리

T-109 구현은 아직 서비스 단계가 아니라는 전제에서 기존 `ops` 내부 ID도 full-prefix로 맞춘다. 새 source registry만 `source_file_id` 스타일을 쓰고 기존 운영 메타데이터가 `release_id`, `snapshot_id`처럼 짧은 이름을 유지하면 API와 DB가 다시 혼재된다. 따라서 T-109 1단계 migration은 기존 `ops` 테이블의 PK/FK/API DTO를 함께 정리한다.

| 현재 column | 확정 column | 대상 |
|-------------|-------------|------|
| `ops.audit_events.event_id` | `audit_event_id` | 감사 이벤트 PK와 API resource id |
| `ops.dataset_snapshots.snapshot_id` | `dataset_snapshot_id` | dataset snapshot PK |
| `ops.dataset_snapshots.parent_snapshot_id` | `parent_dataset_snapshot_id` | snapshot lineage |
| `ops.serving_releases.release_id` | `serving_release_id` | serving release PK |
| `ops.serving_releases.snapshot_id` | `dataset_snapshot_id` | release가 참조하는 snapshot |
| `ops.serving_releases.previous_release_id` | `previous_serving_release_id` | 직전 release |
| `ops.serving_releases.rollback_target_release_id` | `rollback_target_serving_release_id` | rollback 대상 release |
| `ops.maintenance_windows.window_id` | `maintenance_window_id` | maintenance window PK |
| `ops.table_stats_snapshots.stats_id` | `table_stats_snapshot_id` | table stats snapshot PK |

`ops.artifacts.artifact_id`, `load_jobs.job_id`, `load_consistency_reports.report_id`는 이미 의미가 충분히 명확하고 `ops` 외부 public job/report 계약과 연결되어 있으므로 별도 ADR 없이는 바꾸지 않는다. 위 rename은 admin 전용 외부 인터페이스에도 영향을 준다. 구현 PR은 OpenAPI, Python DTO, TypeScript type, CLI 출력, admin route path parameter 이름, migration guide를 함께 갱신해야 한다.

DDL 예시는 가독성을 위해 일부 inline CHECK를 남길 수 있지만, 실제 Alembic/`SCHEMA_SQL` 구현에서는 모든 CHECK/UNIQUE/FK에 명시 constraint/index 이름을 붙인다. 기존 스키마의 `char_length()` 관례를 따라 hash 길이 검증도 `length()`가 아니라 `char_length()`를 사용한다.

### `ops.source_file_groups`

match set이 직접 참조하는 원천 단위다. `single_file` category는 group 하나에 file 하나가 들어가고, `multi_part` category는 group 하나에 여러 part file이 들어간다. 전자지도/출입구/구역의도형의 시도별 17개 ZIP은 `part_kind='sido'`, `part_key=<시도코드>`인 multi-part group의 한 사례다. 향후 국가지점번호 grid layer, 권역별 분할, 월별 보강 자료가 생겨도 같은 모델을 재사용한다.

```sql
CREATE TABLE ops.source_file_groups (
  source_file_group_id  UUID PRIMARY KEY,
  category              TEXT NOT NULL,
  group_kind            TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  user_yyyymm           TEXT NOT NULL,
  inferred_yyyymm       TEXT,
  inferred_yyyymm_basis TEXT,
  yyyymm_mismatch       BOOLEAN NOT NULL DEFAULT false,
  expected_file_count   INTEGER NOT NULL DEFAULT 1 CHECK (expected_file_count >= 1),
  actual_file_count     INTEGER NOT NULL DEFAULT 0 CHECK (actual_file_count >= 0),
  coverage              JSONB NOT NULL DEFAULT '{}'::jsonb,
  group_sha256          TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_file_groups_group_kind
    CHECK (group_kind IN ('single_file', 'multi_part')),
  CONSTRAINT chk_ops_source_file_groups_user_yyyymm
    CHECK (user_yyyymm ~ '^\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_inferred_yyyymm
    CHECK (inferred_yyyymm IS NULL OR inferred_yyyymm ~ '^\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_group_sha256
    CHECK (group_sha256 IS NULL OR char_length(group_sha256) = 64),
  CONSTRAINT chk_ops_source_file_groups_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_file_groups_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  ))
);
```

`user_yyyymm`은 group 단일 정본이다. child file이나 match set item에는 사용자가 입력한 기준년월을 중복 저장하지 않는다. 필요하면 조회 DTO에서 group 값을 투영한다.

`group_sha256`는 child file들의 `(part_kind, part_key, sha256, size_bytes)` 또는 single file의 `(sha256, size_bytes)`를 canonical JSON으로 정렬 직렬화한 뒤 계산한 SHA-256이다. 본문 archive를 다시 읽지 않는다. `part_kind='sido'` group의 coverage에는 17개 시도 코드별 `present/missing/failed` 상태를 저장한다.

권장 index:

```sql
CREATE INDEX idx_ops_source_file_groups_category_yyyymm
  ON ops.source_file_groups (category, user_yyyymm, uploaded_at DESC)
  WHERE state = 'available';

CREATE INDEX idx_ops_source_file_groups_state
  ON ops.source_file_groups (state, updated_at DESC);

CREATE INDEX idx_ops_source_file_groups_incomplete
  ON ops.source_file_groups (category, updated_at DESC)
  WHERE actual_file_count < expected_file_count;
```

group `state`는 child file 상태를 집계한 운영 상태다. `available`은 모든 required child file이 `available`이고 group validation이 `passed` 또는 `warning`일 때만 허용한다. child 중 하나라도 `missing`, `quarantined`, `delete_failed`가 되면 group도 같은 계열 상태로 전환하고, 이를 참조하는 비-active `validated` match set은 `invalid`로, active match set은 `state='active'` 유지 + `integrity_alert=true`로 표시한다(`draft`/`restored_from_backup` 같은 pre-hash 상태는 hash를 요구하는 `invalid`로 가지 않고 유지 — 아래 match set 상태 전이 규칙).

group 파생값(`state`, `validation_state`, `actual_file_count`, `coverage`, `group_sha256`)과 참조 match set 전파는 `recompute_group_aggregates(source_file_group_id)` service 한 곳에서만 계산한다. `register`, reconciliation resolve, child soft/hard-delete, `restore`, `revalidate`, validator version 변경에 따른 재검증은 같은 DB transaction 안에서 이 service를 호출해야 한다. 이 service는 하향 전파(group bad -> 비-active `validated`는 `invalid`, active는 `integrity_alert=true`; `draft`/`restored_from_backup` pre-hash 상태는 유지)와 상향 전파(group recovered -> 비-active `invalid`는 `revalidatable`로 표시; `restored_from_backup`은 모든 참조 group이 `available`가 되면 canonical `source_set_hash`를 먼저 산출한 뒤 `revalidatable`로 전이[M-A 옵션2, 상세는 match set 상태 전이 규칙·`restored_from_backup` 생성 절차]; active는 다음 `validate`에서 `integrity_alert=false` 후보 표시)를 모두 담당한다. restore 직후 object 재연결로 모든 참조 group이 `available`가 되는 같은 transaction에서 이 service가 위 match set 전파(선-hash 산출 포함)를 소유·실행한다. raw SQL repository에 두고, JobQueue 단일 worker 가정에 기대지 않는다.

`recompute_group_aggregates()` 계약은 다음으로 고정한다.

| 항목 | 계약 |
|------|------|
| 입력 | `source_file_group_id`, 실행 actor, 호출 원인(`register`, `reconcile_resolve`, `child_soft_delete`/`child_hard_delete`, `restore`, `revalidate`, `validator_version_change` 등; 위 prose의 필수 호출자 목록과 동일) |
| 출력 | 같은 transaction 안에서 group 파생값, child coverage, 참조 match set state/`integrity_alert` 후보, audit metadata를 갱신한다 |
| 하지 않는 일 | active match set의 `integrity_alert=false` 확정, match set `activate`, rebuild enqueue는 하지 않는다 |
| active 복구 | 모든 group이 회복되면 active match set에 `integrity_alert_detail.recovered=true` 같은 해제 후보만 표시하고, 실제 해제는 `POST /validate`의 active validate-in-place가 수행한다 |
| restored 복구 | `restored_from_backup`은 모든 참조 group이 `available`가 된 같은 transaction에서 canonical `source_set_hash`를 산출한 뒤 `revalidatable`로 전이한다 |

### `ops.source_files`

실제 업로드된 압축 원본 파일의 정본 registry다. 파일 하나는 반드시 하나의 group에 속한다. `single_file` group은 child file이 1개이고, `multi_part` group은 child file이 여러 개다. 같은 archive를 여러 match set에서 재사용하려면 match set은 file이 아니라 group을 참조한다.

```sql
CREATE TABLE ops.source_files (
  source_file_id        UUID PRIMARY KEY,
  source_file_group_id  UUID NOT NULL REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  original_filename     TEXT NOT NULL,
  part_kind             TEXT NOT NULL DEFAULT 'single',
  part_key              TEXT NOT NULL DEFAULT 'archive',
  part_label            TEXT,
  file_role             TEXT,
  content_type          TEXT,
  compression_format    TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  size_bytes            BIGINT NOT NULL CHECK (size_bytes >= 0),
  sha256                TEXT NOT NULL,
  duplicate_of_file_id  UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  storage_kind          TEXT NOT NULL,
  storage_uri           TEXT NOT NULL,
  bucket                TEXT,
  object_key            TEXT,
  object_etag           TEXT,
  object_version_id     TEXT,
  last_verified_etag    TEXT,
  last_verified_size_bytes BIGINT,
  last_verified_at      TIMESTAMPTZ,
  last_deep_verified_at TIMESTAMPTZ,
  rustfs_endpoint_hash  TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_files_part_kind
    CHECK (part_kind IN ('single', 'sido', 'grid_layer', 'custom')),
  CONSTRAINT chk_ops_source_files_sha256
    CHECK (char_length(sha256) = 64),
  CONSTRAINT chk_ops_source_files_last_verified_size
    CHECK (last_verified_size_bytes IS NULL OR last_verified_size_bytes >= 0),
  CONSTRAINT chk_ops_source_files_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_files_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  ))
);
```

위 DDL은 `state`와 `validation_state`를 분리하는 확정 설계다. source registry row는 `register` 단계에서 생성되므로 upload 진행 상태는 upload session이 관리하고, `ops.source_file_groups`/`ops.source_files`에는 저장 완료 이후 상태만 남긴다. `state='available'`일 때 `validation_state IN ('passed','warning')`만 허용하는 CHECK 또는 trigger를 추가해 모순 상태를 막아야 한다.

`source_files`에는 `user_yyyymm`을 두지 않는다. child 기준월이 필요하면 `source_file_group_id`로 group을 조인한다. `part_kind='sido'`일 때 `part_key`는 시도 코드이고 `part_label`은 시도명이다. 이전 문서의 `sido_code`는 이 `part_key`의 특수 사례로만 해석한다.

권장 state:

| state | 의미 |
|-------|------|
| `validating` | 등록 후 재검증 또는 검증 재실행 중 |
| `available` | 정상 검증 완료, match set에 사용 가능 |
| `quarantined` | 파일은 보존하지만 구조/정합성 문제가 있어 기본 선택 금지 |
| `missing` | DB row는 있으나 RustFS object가 없음 |
| `soft_deleted` | UI에서 삭제 처리했지만 감사 목적으로 row 보존 |
| `hard_deleted` | RustFS object까지 삭제된 상태. row는 감사 목적으로 남김 |
| `delete_failed` | hard-delete 요청 중 일부 object 삭제가 실패해 운영자 확인 필요 |

`validation_state` 권장값:

| validation_state | 의미 |
|------------------|------|
| `unknown` | 백업 manifest 기반 stub처럼 과거 검증 결과를 알 수 없음 |
| `not_started` | 아직 구조 검증이 실행되지 않음 |
| `running` | 최신 검증 job 실행 중 |
| `passed` | 구조와 필수 member 검증 통과 |
| `warning` | 필수 조건은 통과했지만 기준년월 mismatch, optional member 누락 같은 경고가 있음 |
| `failed` | 필수 구조 검증 실패 |
| `skipped` | optional 검증 자료 생략 등으로 검증을 의도적으로 생략 |

권장 index:

```sql
CREATE INDEX idx_ops_source_files_group_part
  ON ops.source_files (source_file_group_id, part_kind, part_key);

CREATE INDEX idx_ops_source_files_sha256
  ON ops.source_files (sha256, size_bytes, part_kind, part_key);

CREATE UNIQUE INDEX idx_ops_source_files_object_key
  ON ops.source_files (bucket, object_key)
  WHERE object_key IS NOT NULL AND state <> 'hard_deleted';
```

`sha256 + size_bytes`는 중복 탐지용이지 무조건 unique로 두지 않는다. 같은 파일을 다른 category로 잘못 올린 사례를 UI가 보여줘야 하므로 DB constraint보다 duplicate detection warning이 안전하다.

multi-part category에서는 `(source_file_group_id, part_key)`가 중복되면 안 된다.

```sql
CREATE UNIQUE INDEX idx_ops_source_files_group_part_unique
  ON ops.source_files (source_file_group_id, part_key)
  WHERE state <> 'hard_deleted';
```

### `ops.source_upload_sessions`

multipart upload 진행 상태를 영속화한다. upload session은 storage-first 흐름의 작업 단위이며, registry row는 `register` 전까지 생성하지 않는다. 서버 재시작, 브라우저 중단, 네트워크 재시도 후에도 part 목록과 RustFS multipart upload id를 복구할 수 있어야 한다.

```sql
CREATE TABLE ops.source_upload_sessions (
  source_upload_session_id TEXT PRIMARY KEY,
  source_file_group_id     UUID NOT NULL,
  category                 TEXT NOT NULL,
  group_kind               TEXT NOT NULL,
  user_yyyymm              TEXT NOT NULL,
  display_name             TEXT NOT NULL,
  state                    TEXT NOT NULL,
  expected_file_count      INTEGER NOT NULL CHECK (expected_file_count >= 1),
  uploaded_file_count      INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_file_count >= 0),
  upload_strategy          TEXT NOT NULL CHECK (upload_strategy IN ('multipart')),
  storage_kind             TEXT NOT NULL,
  bucket                   TEXT,
  prefix                   TEXT,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at               TIMESTAMPTZ,
  registration_deadline_at TIMESTAMPTZ,
  completed_at             TIMESTAMPTZ,
  registered_at            TIMESTAMPTZ,
  error_message            TEXT,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_upload_sessions_user_yyyymm
    CHECK (user_yyyymm ~ '^\d{6}$')
);

CREATE TABLE ops.source_upload_session_parts (
  source_upload_session_id TEXT NOT NULL REFERENCES ops.source_upload_sessions(source_upload_session_id) ON DELETE CASCADE,
  part_key                 TEXT NOT NULL,
  multipart_upload_id      TEXT,
  part_number              INTEGER NOT NULL CHECK (part_number >= 1),
  part_etag                TEXT,
  part_sha256              TEXT CHECK (part_sha256 IS NULL OR char_length(part_sha256) = 64),
  received_bytes           BIGINT NOT NULL DEFAULT 0 CHECK (received_bytes >= 0),
  completed_at             TIMESTAMPTZ,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (source_upload_session_id, part_key, part_number)
);
```

미완 multipart upload는 저장소 용량을 소비한다. reconciliation은 RustFS `ListMultipartUploads` 또는 호환 API를 사용할 수 있으면 `issue_type='orphaned_multipart'`로 노출하고, `expires_at`이 지난 session의 multipart upload는 abort 후보로 표시한다. 업로드 재개 시에는 DB에 저장된 `multipart_upload_id`만 믿지 않고 RustFS `ListParts` 또는 호환 API로 해당 multipart upload가 아직 존재하는지 먼저 확인한다. DB에는 part 기록이 있지만 RustFS multipart가 이미 abort/expire된 경우 session을 `failed_storage_state`로 전환하고, 사용자는 해당 slot을 새 multipart upload id로 다시 올리거나 session을 취소해야 한다.

`registration_deadline_at`은 upload가 RustFS 저장까지 끝났지만 registry 등록은 아직 승인되지 않은 정상 대기 상태의 만료 기준이다. deadline 전 object는 reconciliation에서 `object_missing_db`가 아니라 `pending_registration`으로 분류해 삭제 후보에서 제외한다. deadline이 지나면 사용자가 세션 재개, registry 등록, 폐기 중 하나를 선택하도록 UI에 노출한다.

만료 기본값은 설정으로 관리한다. 1차 기본값은 `source_upload_session_ttl_days=7`, `source_registration_deadline_days=30`이다. `expires_at` 전에는 중단된 multipart를 재개할 수 있고, `expires_at` 이후에는 janitor가 미완 multipart upload를 abort한 뒤 session을 `expired` 또는 `cancelled`로 마감한다. RustFS 저장까지 끝난 object는 자동 삭제하지 않는다. `registration_deadline_at`이 지난 미등록 object는 `pending_registration`에서 `registration_expired` issue로 전이하고, 사용자는 registry 등록 재시도, deadline 연장, object 폐기 중 하나를 명시적으로 선택한다.

janitor는 1차 구현에서 PostgreSQL advisory lock을 잡는 admin service/CLI periodic job로 둔다. 기본 주기는 1시간이며, 실행 중 같은 lock을 잡지 못하면 이번 회차를 skip한다. 실패한 abort/delete 보조 작업은 다음 회차에서 재시도하되, 미완 multipart만 자동 abort 대상이고 RustFS 저장 완료 object는 자동 삭제하지 않는다. janitor 실행 결과는 처리한 session 수, abort 성공/실패 수, `registration_expired` 전이 수를 audit event와 metric에 남긴다.

### `ops.source_file_members`

압축파일 내부 member/layer 검증 결과다. 시도별 ZIP 17개, SHP sidecar, TXT member, DBF field summary를 관리한다.

```sql
CREATE TABLE ops.source_file_members (
  source_file_member_id UUID PRIMARY KEY,
  source_file_id     UUID NOT NULL REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  member_path        TEXT NOT NULL,
  member_kind        TEXT NOT NULL,
  part_kind          TEXT,
  part_key           TEXT,
  part_label         TEXT,
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
- `electronic_map_full`: 시도별 ZIP 내부 11개 master layer의 `.shp/.shx/.dbf`
- `roadaddr_entrance_full`: `RNENTDATA_*.txt` 17개
- `zone_shape_full`: `TL_SPPN_MAKAREA.{shp,shx,dbf}` 17개

### `ops.source_file_validations`

검증 실행 이력이다. 같은 group/file도 validator 버전이 바뀌면 재검증할 수 있다. `scope='group'`은 시도별 17개 coverage, category-level 필수 구조, 기준년월 mismatch 같은 집계 검증을 뜻하고, `scope='file'`은 개별 archive 내부 member 검증을 뜻한다.

```sql
CREATE TABLE ops.source_file_validations (
  source_file_validation_id UUID PRIMARY KEY,
  source_file_group_id UUID NOT NULL REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  scope               TEXT NOT NULL CHECK (scope IN ('group', 'file')),
  validator_version   TEXT NOT NULL,
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  stage               TEXT,
  progress            DOUBLE PRECISION NOT NULL DEFAULT 0,
  error_code          TEXT,
  error_message       TEXT,
  log_tail            TEXT,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (
    (scope = 'group' AND source_file_id IS NULL)
    OR (scope = 'file' AND source_file_id IS NOT NULL)
  )
);
```

### `ops.consistency_case_definitions`

C1~C10과 T-109 이후 C11+의 case metadata 정본이다. 기존 `kortravelgeo.core.consistency_definitions.CASE_DEFINITIONS`는 이 테이블의 seed 근거로만 사용하고, admin UI는 API가 이 테이블에서 읽어 내려주는 정의를 렌더링한다.

```sql
CREATE TABLE ops.consistency_case_definitions (
  consistency_case_code TEXT PRIMARY KEY CHECK (consistency_case_code ~ '^C\d+$'),
  display_order         INTEGER NOT NULL,
  name                  TEXT NOT NULL,
  compares              TEXT NOT NULL,
  abnormal_criteria     TEXT NOT NULL,
  evidence              JSONB NOT NULL DEFAULT '[]'::jsonb,
  likely_causes         JSONB NOT NULL DEFAULT '[]'::jsonb,
  decision_guide        TEXT NOT NULL,
  threshold             TEXT,
  default_severity      TEXT,
  state                 TEXT NOT NULL CHECK (state IN ('enabled', 'disabled', 'retired')),
  skip_policy           JSONB NOT NULL DEFAULT '{}'::jsonb,
  sample_schema         JSONB NOT NULL DEFAULT '{}'::jsonb,
  introduced_by         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE ops.consistency_case_inputs (
  consistency_case_code TEXT NOT NULL REFERENCES ops.consistency_case_definitions(consistency_case_code) ON DELETE RESTRICT,
  category              TEXT NOT NULL,
  required              BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (consistency_case_code, category)
);
```

권장 index:

```sql
CREATE UNIQUE INDEX idx_ops_consistency_case_definitions_display_order
  ON ops.consistency_case_definitions (display_order)
  WHERE state <> 'retired';
```

운영 규칙:

- migration은 기존 C1~C10을 seed하고, C11+는 T-109 validation 확장 구현에서 추가한다.
- seed source는 `kortravelgeo.core.consistency_definitions.CASE_DEFINITIONS`와 `kortravelgeo.dto.admin.ConsistencyCaseDefinition`이다. 컬럼 매핑은 `code -> consistency_case_code`, `name -> name`, `compares -> compares`, `abnormal_criteria -> abnormal_criteria`, `evidence -> evidence`, `likely_causes -> likely_causes`, `decision_guide -> decision_guide`, `threshold -> threshold`다.
- `default_severity`는 C11+부터 명시 입력을 권장한다. C1~C10은 기존 `threshold`/case runner의 severity 산출 규칙을 유지할 수 있도록 NULL을 허용한다.
- `ops.consistency_case_inputs`는 category 이름이 catalog에 없는 경우 seed 또는 migration 단계에서 실패시킨다. category 이름 변경/retire 시 C11+ 입력 참조가 조용히 깨지지 않게 하기 위한 최소 검증이다.
- case code는 재사용하지 않는다. 더 이상 쓰지 않는 case는 row 삭제가 아니라 `state='retired'`로 전환한다.
- API는 `GET /v1/admin/consistency/case-definitions`를 제공하고, UI는 C1~C10을 하드코딩하지 않는다.
- `ops.consistency_case_samples.case_code`는 기존 TEXT 값을 유지하되, FK를 추가할 수 있으면 `ops.consistency_case_definitions(consistency_case_code)`를 참조한다. 기존 report가 registry seed보다 먼저 존재하는 복원 DB에서는 FK 추가 전에 seed를 먼저 수행한다.

### `ops.source_storage_reconcile_runs`

RustFS와 DB registry의 일관성 검증 실행 단위다.

```sql
CREATE TABLE ops.source_storage_reconcile_runs (
  source_storage_reconcile_run_id UUID PRIMARY KEY,
  prefix              TEXT NOT NULL,
  mode                TEXT NOT NULL DEFAULT 'quick' CHECK (mode IN ('quick', 'deep')),
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  scanned_objects     BIGINT NOT NULL DEFAULT 0,
  scanned_db_files    BIGINT NOT NULL DEFAULT 0,
  rehashed_objects    BIGINT NOT NULL DEFAULT 0,
  skipped_rehash_objects BIGINT NOT NULL DEFAULT 0,
  cursor              JSONB NOT NULL DEFAULT '{}'::jsonb,
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
  source_storage_reconcile_item_id UUID PRIMARY KEY,
  source_storage_reconcile_run_id UUID NOT NULL REFERENCES ops.source_storage_reconcile_runs(source_storage_reconcile_run_id) ON DELETE CASCADE,
  issue_type          TEXT NOT NULL,
  source_file_group_id UUID REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE SET NULL,
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
| `pending_registration` | RustFS object는 있지만 upload session이 아직 registry 등록 대기 중 | 삭제 후보가 아니다. 세션 재개, registry 등록, 세션 폐기 중 선택 |
| `registration_expired` | RustFS object는 있지만 upload session의 `registration_deadline_at`이 지남 | registry 등록 재시도, deadline 연장, object 폐기 중 선택 |
| `source_file_unavailable` | 백업/복원 manifest에는 원천 파일 metadata가 있으나 현재 bucket에 object가 없음 | object 재업로드/재연결 또는 재구성 불가로 승인 |
| `source_file_group_incomplete` | multi-part group의 필수 child file coverage가 깨짐 | 누락 part 재업로드/재연결 또는 group invalid 유지 |
| `size_mismatch` | object size가 DB와 다름 | object 재다운로드/hash 확인 후 quarantine 또는 hash/size 재기록 |
| `hash_mismatch` | SHA-256이 다름 | 손상 가능성으로 기본 사용 금지. 사용자가 재해시 후 `update_hash_after_verify` 또는 삭제 |
| `etag_mismatch` | ETag만 다름 | multipart/metadata 차이 가능. size/hash가 같으면 정보성으로 resolve 가능 |
| `duplicate_object` | 같은 sha256/size object가 여러 key에 있음 | 하나를 유지하고 나머지는 soft delete 후보로 표시 |
| `orphaned_multipart` | RustFS에 완료되지 않은 multipart upload가 남아 있음 | 만료된 upload session이면 abort, 아직 진행 중이면 보류 |
| `delete_failed` | 사용자가 삭제를 승인했지만 RustFS delete가 실패함 | backoff 후 재시도, object head 재확인, 삭제 포기 기록 중 선택 |

`hash_mismatch`에서 "hash 일치화"는 단순히 DB 값을 object 값으로 덮어쓰는 버튼이 아니다. 서버가 object를 다시 읽어 SHA-256을 계산하고, 사용자가 "현재 object를 새 정본으로 인정"한다는 확인을 해야만 `ops.source_files.sha256`을 갱신한다. 그 전까지는 해당 파일을 match set에 사용할 수 없게 한다.

reconciliation mode:

| mode | 동작 |
|------|------|
| `quick` | object list/head를 수행한다. `size`, `etag`가 `source_files.last_verified_size_bytes`, `last_verified_etag`와 같으면 본문 재해시를 생략한다. 변경되었거나 이전 검증 기록이 없으면 해당 object만 deep rehash한다. |
| `deep` | 대상 prefix 또는 선택된 object 범위를 전부 streaming rehash한다. 중단/재개를 위해 `cursor`에 마지막 object key와 집계 상태를 저장한다. |

ADR-049의 "object 전체 재해시로 hash mismatch를 즉시 확정" 원칙은 `deep` 또는 변경 감지 object에 적용한다. 정기 scan 기본값은 `quick`으로 두어 매 회 전국 수~십 GiB를 다시 읽는 운영 비용을 피한다.

권장 index:

```sql
CREATE INDEX idx_ops_source_storage_reconcile_items_run_state
  ON ops.source_storage_reconcile_items (source_storage_reconcile_run_id, state);

CREATE INDEX idx_ops_source_storage_reconcile_items_object_key
  ON ops.source_storage_reconcile_items (object_key)
  WHERE object_key IS NOT NULL;
```

### `ops.source_match_sets`

DB 재구성 또는 검증 실행에 사용할 파일 조합의 상위 객체다.

```sql
CREATE TABLE ops.source_match_sets (
  source_match_set_id      UUID PRIMARY KEY,
  name                     TEXT NOT NULL,
  description              TEXT,
  profile                  TEXT NOT NULL,
  state                    TEXT NOT NULL,
  source_set_hash          TEXT,
  mixed_yyyymm             BOOLEAN NOT NULL DEFAULT false,
  yyyymm_by_category       JSONB NOT NULL DEFAULT '{}'::jsonb,
  omitted_optional         JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at             TIMESTAMPTZ,
  last_load_job_id         TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  last_consistency_report_id TEXT REFERENCES load_consistency_reports(report_id) ON DELETE SET NULL,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  integrity_alert          BOOLEAN NOT NULL DEFAULT false,
  integrity_alert_at       TIMESTAMPTZ,
  integrity_alert_detail   JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_sets_state
    CHECK (state IN ('draft', 'validated', 'active', 'retired', 'invalid', 'revalidatable', 'restored_from_backup')),
  CONSTRAINT chk_ops_source_match_sets_source_set_hash
    CHECK (
      (state = 'draft' AND source_set_hash IS NULL)
      OR (state = 'restored_from_backup' AND (source_set_hash IS NULL OR char_length(source_set_hash) = 64))
      OR (state NOT IN ('draft', 'restored_from_backup') AND source_set_hash IS NOT NULL AND char_length(source_set_hash) = 64)
    )
);
```

`source_set_hash`는 match set item을 category, `source_file_group_id`, `source_file_group.group_sha256`, `effective_yyyymm`, `omitted`, `omitted_reason` 순서로 canonical JSON 직렬화한 뒤 SHA-256 hex로 계산한다. `draft` 상태에서는 item이 아직 비어 있거나 빠질 수 있으므로 NULL을 허용한다. `restored_from_backup`은 legacy manifest에 canonical hash가 없을 수 있어 NULL을 허용하되, hash가 있으면 64자여야 한다. 참조 group이 모두 `available`이고 `group_sha256 IS NOT NULL`일 때만 `validate`에서 hash를 산출한다. item이 추가/삭제/변경되면 `validate` 단계에서 항상 재계산하고, `activate` 직전 다시 한 번 재계산해 stale hash를 막는다. 단, `restored_from_backup`은 `source_set_hash` CHECK(`revalidatable` 이상은 hash NOT NULL 요구) 충돌을 피하기 위해 **`revalidatable` 진입 전에 canonical hash를 선산출**하고(M-A 옵션 2), 이후 `validate`에서 그 hash를 재검산·확정한다(즉 복원 경로에서는 hash 산출이 `validate`보다 앞선다).

active match set은 한 건만 허용한다.

```sql
CREATE UNIQUE INDEX idx_ops_source_match_sets_one_active
  ON ops.source_match_sets (state)
  WHERE state = 'active';
```

`integrity_alert`는 원천 무결성 결손을 `state`와 **분리**한 플래그다. one-active index가 `WHERE state='active'`이므로, active match set이 참조하는 group이 missing/quarantined가 되었다고 `state`를 `invalid`로 바꾸면 슬롯이 비어 '현재 구성=알수없음'이 되고 "슬롯 유지"와 모순된다. 따라서 **active match set은 결손 시에도 `state='active'`를 유지하고 `integrity_alert=true`(+`integrity_alert_at`, 누락 object를 `integrity_alert_detail`)로만 표시**한다. `state='invalid'` 전환은 비-active `validated` match set에 적용한다(`draft`/`restored_from_backup`은 canonical hash가 없는 pre-hash 상태라 hash를 요구하는 `invalid`로 가지 않는다). 이러면 one-active 슬롯·serving 유지·재구성 불가 경고가 모두 모순 없이 성립한다.

active serving release와 match set 연결은 `ops.dataset_snapshots.source_match_set_id` FK를 정본으로 삼는다. full-prefix rename 이후에는 `ops.serving_releases.dataset_snapshot_id`를 통해 current snapshot을 찾고, 그 snapshot의 `source_match_set_id`로 현재 원천 조합을 찾는다. 백업 복원처럼 T-109 registry가 없는 legacy 데이터는 `ops.dataset_snapshots.source_set` JSONB 안의 `source_match_set` snapshot을 read-only fallback으로만 표시한다.

필수 migration:

```sql
ALTER TABLE ops.dataset_snapshots
  ADD COLUMN source_match_set_id UUID
  REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE SET NULL;

CREATE INDEX idx_ops_dataset_snapshots_source_match_set_id
  ON ops.dataset_snapshots (source_match_set_id)
  WHERE source_match_set_id IS NOT NULL;
```

`ON DELETE SET NULL`은 FK 때문에 오래된 snapshot lineage가 물리 정리를 영구 차단하지 않게 하는 안전장치다. T-109의 실제 운영 정책은 `ops` registry row를 물리 삭제하지 않는 것이며, match set 삭제/retire는 application guard와 audit event로 통제한다.

권장 state:

| state | 의미 |
|-------|------|
| `draft` | 사용자가 조합 중 |
| `validated` | 모든 필수 파일과 선택 검증 skip flag가 확인됨 |
| `active` | 현재 serving release 또는 rebuild 작업의 기준 |
| `retired` | 더 이상 기본 선택하지 않음 |
| `invalid` | 참조 group/child file이 missing/quarantined가 된 **비-active `validated`** match set의 사용 불가 상태 (active는 `state='active'` 유지 + `integrity_alert=true`; `draft`/`restored_from_backup` pre-hash는 invalid로 가지 않음) |
| `revalidatable` | `invalid` 또는 `restored_from_backup` 원천이 다시 검증 가능해져, 명시 validate 후 usable state로 갈 수 있음(`invalid`였으면 직전 usable state, `restored_from_backup`이었으면 `validated`). 이 상태부터 `source_set_hash`는 항상 NOT NULL이다(진입 전 산출) |
| `restored_from_backup` | 백업 manifest에서 재구성한 read-only match set |

상태 전이 규칙:

- `activate`는 `validated` 상태에서만 가능하다. `draft`, `invalid`, `revalidatable`, `restored_from_backup`은 직접 active로 승격할 수 없다.
- `activate`는 advisory lock + 단일 DB transaction에서 기존 active를 `retired`로 바꾼 뒤 새 match set을 `active`로 세우는 atomic swap이다. `idx_ops_source_match_sets_one_active`는 deferrable constraint가 아니므로 retire→activate 순서로 수행하며, transaction 내부의 순간 상태가 아니라 **외부에서 관찰 가능한 active gap(0건)이나 unique 위반을 만들지 않는** 것이 요건이다.
- `retire`는 active serving release가 참조 중인 match set에 대해 typed confirmation을 요구한다. active match set을 retire하면 current source UI가 `알수없음`으로 떨어질 수 있으므로 replacement activate와 같은 transaction에서 처리하는 것을 기본으로 한다.
- 참조 group/file이 `missing`/`quarantined`로 바뀌면 match set의 무결성 결손을 표시하되 **active 여부에 따라 다르게** 처리한다(`state`와 `integrity_alert` 분리):
  - **비-active 중 `validated`**는 `state='invalid'`로 전환한다. `draft`/`restored_from_backup`은 아직 canonical hash가 없는 pre-hash 상태이므로 hash를 요구하는 `invalid`로 가지 않고 각자 상태를 유지한다(`draft`는 그대로, `restored_from_backup`은 object 재연결로만 진행).
  - **active**는 `state='active'`를 유지하고 `integrity_alert=true`(+`integrity_alert_at`, 누락 object 목록은 `integrity_alert_detail`)로만 표시한다. one-active 슬롯을 비우지 않으므로 '현재 구성'은 계속 이 match set을 가리키고, 이미 만들어진 serving DB는 즉시 장애가 아니다. UI는 "현재 serving은 유지되지만 원천 archive 결손으로 같은 DB를 재구성할 수 없음" 배지와 누락 object 목록을 표시한다.
  - 이 active/비-active 구분은 reconcile resolve, rebuild 적재 전 게이트, run-validation 무결성 실패 등 참조 group이 missing/quarantined가 되는 **모든 경로**에 동일하게 적용한다.
- 결손 원인이 모두 해소되어 참조 group이 다시 `available`이 되면:
  - 비-active `invalid`는 자동 복귀가 아니라 `revalidatable`로 표시하고, 운영자가 `validate`를 실행해 canonical hash·coverage가 다시 맞으면 `validated`로 복귀한다(active 승격은 별도 `activate` atomic swap).
  - active(`integrity_alert=true`)는 `POST /validate`를 active validate-in-place로 실행할 수 있다. 성공 시 `integrity_alert=false`, `integrity_alert_detail={}`로 내리며 `state='active'`를 그대로 유지한다(슬롯 변동 없음). 실패하면 `state='active'`와 `integrity_alert=true`를 유지하고 실패 원인을 audit/report에 남긴다.
- `restored_from_backup`은 모든 참조 group이 object 재연결·구조 검증으로 `available`가 되면, **그 시점에 canonical `source_set_hash`를 먼저 산출**(legacy manifest로 NULL이던 경우 새로 계산)한 뒤 `revalidatable`로 전이한다. 즉 `revalidatable` 진입 시 hash가 이미 채워져 있어 `source_set_hash` CHECK(비-`draft`/비-`restored_from_backup`은 hash NOT NULL 요구)를 위반하지 않는다(**M-A 옵션 2**: hash 산출을 전이의 선행 조건으로 둔다). 이후 운영자가 `validate`를 실행해 그 hash·coverage가 일치하면 `validated`로 복귀하고, active 승격은 일반 `validated`→`active` atomic swap을 따른다. (group/file은 `missing`→`validating`→`available`의 별개 상태머신이며, match set의 `restored_from_backup`→`revalidatable`→`validated`와 섞지 않는다.)
- 새 match set을 `activate`하면 기존 active(무결성 결손으로 `integrity_alert=true`였든 아니든)는 같은 transaction에서 `retired`로 전환된다.
- rollback은 activate와 같은 one-active invariant를 따른다. rollback 대상 snapshot이 `source_match_set_id`를 갖고 있으면 PostgreSQL advisory lock + 단일 transaction에서 현재 active match set을 `retired`로 내리고 rollback 대상 match set을 `active`로 복원한다. 대상 match set의 `integrity_alert`는 rollback 직전 source quick reconcile 결과로 재계산하며, source 결손이 있으면 `active + integrity_alert=true`로 복원하고 UI에 재구성 불가 경고를 표시한다. rollback 대상 snapshot이 legacy라 FK가 없으면 match set 상태를 만들지 않고 `알수없음/추정`으로만 표시한다.

### `ops.source_match_set_items`

match set에 포함된 category별 원천 group 또는 생략 기록이다. `single_file` category도 group을 참조하므로 match set API와 rebuild bridge는 항상 같은 식별자(`source_file_group_id`)만 다룬다.

```sql
CREATE TABLE ops.source_match_set_items (
  source_match_set_item_id UUID PRIMARY KEY,
  source_match_set_id      UUID NOT NULL REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE CASCADE,
  category                 TEXT NOT NULL,
  role                     TEXT NOT NULL,
  source_file_group_id     UUID REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  required                 BOOLEAN NOT NULL DEFAULT false,
  omitted                  BOOLEAN NOT NULL DEFAULT false,
  omitted_reason           TEXT,
  effective_yyyymm         TEXT,
  validation_enabled       BOOLEAN NOT NULL DEFAULT true,
  load_order               INTEGER,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_set_items_role
    CHECK (role IN ('build_required', 'build_recommended', 'validation_optional', 'enrichment_candidate')),
  CONSTRAINT chk_ops_source_match_set_items_omitted
    CHECK (
    (omitted = false AND source_file_group_id IS NOT NULL)
    OR (omitted = true AND source_file_group_id IS NULL)
  ),
  UNIQUE (source_match_set_id, category)
);
```

`source_file_group_id` FK는 참조 무결성 방어다. T-109의 삭제 정책은 row를 지우지 않고 `ops.source_file_groups.state`와 `ops.source_files.state`를 바꾸는 방식이므로, active/draft match set이 참조 중인 group/file의 `hard_deleted` 전환은 application guard와 audit event로 막는다. `UNIQUE (source_match_set_id, category)`는 category당 하나의 registry group만 허용한다. 시도별 ZIP 17개처럼 여러 파일로 구성되는 자료도 하나의 `source_file_group_id` 아래 `ops.source_files` 17행으로 보존하고, match set은 그 group 하나를 참조한다.

`effective_yyyymm` 산출 규칙:

1. 기본값은 `ops.source_file_groups.user_yyyymm`이다.
2. archive 내부 member 기준월이 더 신뢰 가능한 category는 `metadata.effective_yyyymm_basis='member_filename'`으로 기록할 수 있다. 그래도 저장 정본은 사용자가 확정한 group `user_yyyymm`이고, `effective_yyyymm`은 serving/검증 판단용 파생값이다.
3. `inferred_yyyymm`과 `user_yyyymm`이 다르면 `yyyymm_mismatch=true`와 warning을 남긴다. 서버가 조용히 자동 수정하지 않는다.
4. `roadaddr_entrance_full`처럼 상위 디렉터리와 내부 member 기준월이 다를 수 있는 category는 `inferred_yyyymm_basis`를 반드시 기록한다.
5. `ops.source_match_sets.yyyymm_by_category`와 `mixed_yyyymm`은 item validate/activate 때 item들의 `effective_yyyymm`에서 재계산한다.

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

optional 내부 member:

- `match_jibun_*.txt` 17개

검증:

- 7z 해제 가능 여부를 확인한다.
- `match_build_*.txt`와 `match_rs_entrc.txt`가 없으면 실패한다.
- `match_jibun_*.txt`는 없으면 `navi_full`의 `metadata.match_jibun_present=false`와 validation input `skipped`로 기록한다. 독립 match set category로 만들지 않는다.
- 현 텍스트 로더가 직접 7z를 읽지 못하면 load 시 materialization 계획에 `extract_required=true`를 남긴다.

loader 매핑:

- `navi_load`
- `match_jibun_*.txt`는 T-109 1차 구현에서 loader 대상이 아니라 validation candidate다.

### `electronic_map_full`

허용 입력:

- 시도별 ZIP 17개를 한 category 업로드 세션에 업로드
- `도로명주소 전자지도/YYYYMM/<시도>.zip` 형태의 prefix import
- 압축 해제된 시도별 디렉터리는 개발/로더 materialization 검증용 import로만 허용한다. 운영 UI의 정규 업로드 단위는 시도별 개별 ZIP이다.

구조 검증 필수 layer:

- `TL_SCCO_CTPRVN`
- `TL_SCCO_SIG`
- `TL_SCCO_EMD`
- `TL_SCCO_LI`
- `TL_KODIS_BAS`
- `TL_SPRD_MANAGE`
- `TL_SPRD_INTRVL`
- `TL_SPRD_RW`
- `TL_SPBD_BULD`
- `TL_SPBD_EQB`
- `TL_SPBD_ENTRC`

현행 `kortravelgeo.loaders.juso_map.discover_sido_dataset`는 master layer 11개가 모두 없으면 dataset discovery를 실패시킨다. 따라서 T-109 validator도 11개 layer를 모두 필수로 본다. 이 중 serving load 1차 대상은 기존 `shp_polygons_load`가 사용하는 9개 layer이고, `TL_SPBD_EQB`와 `TL_SPBD_ENTRC`는 구조 정상성 검증과 후속 C11/C13 후보 비교에 사용한다. 두 layer를 optional로 낮추지 않는다.

각 layer는 최소 `.shp`, `.shx`, `.dbf` sidecar를 요구한다. `.prj`는 있으면 저장하고 없으면 EPSG:5179 기본 가정 여부를 validation summary에 남긴다.

검증:

- 시도별 ZIP 17개 coverage
- 내부 시도코드 디렉터리 존재
- 11개 layer sidecar 존재
- DBF header field presence
- layer별 검증 profile 확인. `TL_SPRD_INTRVL`은 geometry가 없는 DBF-only road interval layer이므로 geometry sample 검증을 적용하지 않고 DBF field/record 검증만 수행한다.
- geometry layer는 geometry type이 기대값과 맞는지 sample 확인
- SHP/DBF header 검증은 필요한 header byte만 부분 read한다. `Path.read_bytes()[:100]`처럼 전체 수백 MB 파일을 읽은 뒤 앞부분만 쓰는 방식은 17개 시도와 11개 layer에서 GB 단위 불필요 I/O를 만든다.

loader 매핑:

- `shp_polygons_load(mode='full')`. 이 loader의 현 serving 적재 대상은 `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`, `TL_SPRD_MANAGE`, `TL_SPRD_INTRVL`, `TL_SPRD_RW`, `TL_SPBD_BULD` 9개다. `TL_SPBD_EQB`와 `TL_SPBD_ENTRC`는 T-109 registry/validation에서는 필수 구조 layer이지만 1차 serving load에는 섞지 않는다.

### `roadaddr_entrance_full`

허용 입력:

- `도로명주소 출입구 정보/YYYYMM/<시도>.zip` 17개를 한 category 업로드 세션에 업로드
- 각 시도 ZIP 내부의 `RNENTDATA_*.txt`

필수 내부 구조:

- 전국 group 기준 `RNENTDATA_*.txt` 17개 coverage. 개별 시도 ZIP에는 해당 시도 member가 들어 있어야 한다.

검증:

- 내부 파일명 `RNENTDATA_2605_*`처럼 `YYMM` 기준월을 추론한다.
- 상위 디렉터리 기준월과 내부 파일 기준월이 다르면 내부 파일 기준월을 `inferred_yyyymm_basis='member_filename'`으로 우선 표시한다.
- `user_yyyymm`과 `roadname_hangul_full.user_yyyymm`이 다르면 same-month 좌표 승격이 되지 않을 수 있음을 match set builder에서 경고한다.

loader 매핑:

- `roadaddr_entrance_load`

### `zone_shape_full`

허용 입력:

- `구역의도형/YYYYMM/<시도>.zip` 17개를 한 category 업로드 세션에 업로드
- 압축 해제 디렉터리는 개발/로더 materialization 검증용 import로만 허용한다.

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

- 시도별 ZIP 17개 coverage와 `TL_SPPN_MAKAREA` 전국 coverage
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

category upload session은 다음 state를 가진다. `single_file`은 archive 하나, `multi_part`는 같은 session 안의 part archive 여러 개를 대상으로 한다. 시도별 자료는 `part_kind='sido'`와 17개 `part_key`를 사용한다.

```text
created
  -> uploading
  -> uploaded_to_temp
  -> storing_to_rustfs
  -> verifying_rustfs_object
  -> extracting
  -> validating_structure
  -> hashing
  -> duplicate_check
  -> awaiting_registration
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
failed_storage_state
failed_register
cancelled
```

중요 원칙:

- `source_file_group_id`와 child `source_file_id`는 upload session 생성 시 예약할 수 있지만, `ops.source_file_groups`와 `ops.source_files` row는 `register` 단계 전까지 만들지 않는다.
- `ops.source_files` child row는 `register` 단계에서 생성한다. 그 전 실패는 upload session 기록과 RustFS object metadata에 남긴다.
- `uploaded_to_temp` 이전 실패는 RustFS에 object를 만들지 않는다.
- `storing_to_rustfs` 중 실패하면 multipart upload를 abort하거나 partial object를 삭제한다. 일반 prefix에 partial archive가 남으면 안 된다.
- `registered` 이후 실패는 DB row를 삭제하지 않고 `quarantined` 또는 `missing`으로 표시한다.
- 브라우저 업로드 progress는 byte 기반 percent 필수다.
- 서버 내부 검증 단계는 가능한 경우 `processed_bytes / total_bytes` percent를 제공한다. ZIP/7z member scan처럼 정확한 percent가 어려우면 spinner와 현재 stage text를 제공한다.

상태 매핑:

| upload session state | RustFS object | group registry | child file registry | 최종 처리 |
|----------------------|---------------|----------------|---------------------|-----------|
| `created` | 없음 | 없음 | 없음 | 기준년월이 포함된 세션 생성 |
| `uploading` | multipart upload 진행 중 | 없음 | 없음 | 브라우저 업로드 percent 표시 |
| `uploaded_to_temp` | 없음 또는 multipart 임시 상태 | 없음 | 없음 | temp archive만 존재 |
| `storing_to_rustfs` | multipart complete 전후 | 없음 | 없음 | RustFS 저장 진행 |
| `verifying_rustfs_object` | 있음 | 없음 | 없음 | size/etag/metadata/hash 확인 |
| `extracting` | 있음 | 없음 | 없음 | temp extract/materialize 진행 |
| `validating_structure` | 있음 | 없음 | 없음 | category validator 진행 |
| `hashing` | 있음 | 없음 | 없음 | archive SHA-256와 group SHA-256 계산 |
| `duplicate_check` | 있음 | 없음 | 없음 | 기존 registry 중복 후보 표시 |
| `awaiting_registration` | 있음 | 없음 | 없음 | 사용자가 세션 기준년월, mismatch, 검증 결과를 확인하고 등록 승인 대기 |
| `registered` | 있음 | `state='available'` 또는 `quarantined` | `state='available'` 또는 `quarantined` | registry row와 members/validations insert |
| `available` | 있음 | `state='available'` | `state='available'` | match set 선택 가능 |
| `failed_upload` | 없음 | 없음 | 없음 | 세션 실패 |
| `failed_extract` | 있음 또는 없음 | 없음 | 없음 | 세션 실패. 사용자가 재시도 또는 취소 |
| `failed_structure` | 있음 | 없음 | 없음 | registry 등록 전 실패. 사용자가 보존을 선택하면 `register`에서 `quarantined` row로 등록 가능 |
| `failed_hash` | 있음 또는 없음 | 없음 | 없음 | 세션 실패 |
| `failed_rustfs_put` | partial object 가능 | 없음 | 없음 | multipart abort 또는 partial cleanup |
| `failed_rustfs_verify` | 있음 | 없음 | 없음 | object 재검증/삭제 또는 `quarantined` 등록 선택 |
| `failed_storage_state` | DB part 기록과 RustFS multipart 상태 불일치 | 없음 | 없음 | RustFS multipart upload id가 없거나 part 목록이 맞지 않음. slot 재업로드 또는 session 취소 필요 |
| `failed_register` | 있음 | 없음 또는 transaction rollback | 없음 또는 transaction rollback | 같은 session에서 `register` 재시도 가능 |
| `cancelled` | 없음 또는 저장 object | 없음 | 없음 | temp cleanup. 저장 object는 삭제 또는 미등록 object로 reconciliation 노출 |

## RustFS 저장 규칙

storage-first 흐름에서 원본 archive object key는 category와 사용자가 입력한 기준년월을 prefix에 포함한다. 무기한 보존 object가 upload session UUID 아래 흩어지면 기준년월/연도별 scan, archive tier 이동, 용량 집계가 비효율적이기 때문이다. 정본 식별자는 DB registry의 `source_file_group_id`/`source_file_id`이고, `source_upload_session_id`는 metadata로만 남긴다.

```text
<prefix>/source-files/<category>/<user_yyyymm>/<source_file_group_id>/<source_file_id>/<part_key>/<original_filename>
```

예:

```text
kor-travel-geo/source-files/roadname_hangul_full/202605/group-3f.../file-7a.../archive/202605_도로명주소 한글_전체분.zip
kor-travel-geo/source-files/electronic_map_full/202604/group-8b.../file-11.../11/서울특별시.zip
```

object metadata:

| metadata | 값 |
|----------|----|
| `x-amz-meta-ktg-source-file-group-id` | `source_file_group_id` |
| `x-amz-meta-ktg-source-file-id` | `source_file_id` |
| `x-amz-meta-ktg-upload-session-id` | `source_upload_session_id` |
| `x-amz-meta-ktg-category` | category |
| `x-amz-meta-ktg-part-kind` | `single`, `sido`, `grid_layer`, `custom` |
| `x-amz-meta-ktg-part-key` | `archive`, 시도 코드, grid layer 이름 등 |
| `x-amz-meta-ktg-upload-user-yyyymm` | 업로드 세션 생성 시 사용자가 입력한 기준년월 |
| `x-amz-meta-ktg-sha256` | archive SHA-256 |
| `x-amz-meta-ktg-size-bytes` | archive size |
| `x-amz-meta-ktg-registration-state` | `pending_registration`, `registered`, `quarantined` 등 registry 등록 진행 상태 |

RustFS가 metadata를 안정적으로 보존하지 못하거나 S3 호환 차이가 있으면 DB 값을 우선한다. reconciliation은 object metadata가 없을 때도 object key의 `<category>/<user_yyyymm>/<group>/<file>/<part_key>` 구조, size, etag만으로 미등록 object 후보를 표시하고, 사용자가 category/기준년월을 확인해 import하도록 한다. object metadata의 `upload-user-yyyymm`은 세션 생성 시 사용자가 입력한 값이며, 최종 등록 후 기준년월의 정본은 `ops.source_file_groups.user_yyyymm`이다.

현행 `RustfsClient`는 `put_file`, `download_file`, `list_objects` 중심이므로 T-109 구현 전에 다음 메서드를 추가한다.

| 메서드 | 용도 | 주의 |
|--------|------|------|
| `head_object(key)` | register 전후 size/etag/metadata 확인 | SHA-256은 ETag와 같다고 가정하지 않는다. |
| `delete_object(key)` | hard-delete, reconciliation 미등록 object 삭제 | active match set 참조 여부와 typed confirmation을 먼저 확인한다. |
| `put_file(key, path, sha256=..., metadata=...)` | `x-amz-meta-ktg-*` metadata 저장 | RustFS/S3 호환 차이로 metadata가 사라질 수 있으므로 DB가 정본이다. |
| `create_multipart_upload`, `upload_part`, `complete_multipart_upload`, `abort_multipart_upload` | 재시작 가능한 대용량 업로드 | part checksum/etag를 upload session에 저장해 중단 후 재개한다. |
| `list_multipart_uploads(prefix)` | 미완 multipart upload reconciliation | RustFS/S3 호환성에 따라 지원 여부를 feature flag로 노출한다. |
| `rehash_object(key)` | deep reconciliation과 변경 감지 object SHA-256 재계산 | ETag를 hash로 쓰지 않고 object 본문을 streaming으로 읽어 계산한다. |

reconciliation 기본 scan은 `quick` 모드로 object list/head를 수행하고, 직전 검증의 size/etag와 달라진 object 또는 검증 이력이 없는 object만 본문을 다시 읽어 SHA-256을 재계산한다. 사용자가 `deep` 모드를 실행하거나 손상 의심 항목을 resolve할 때는 대상 object 전체를 streaming rehash해 `hash_mismatch`를 즉시 확정한다. `hash_mismatch`가 확인되면 해당 file/group은 match set 선택 대상에서 제외하고, 사용자가 재업로드·삭제·typed confirmation 기반 hash 갱신 중 하나를 선택한다.

같은 `size`·`etag`로 내용만 바뀐 변조는 `quick` scan이 놓칠 수 있다. 이를 막기 위해 `last_deep_verified_at`이 설정 기간(기본 `source_deep_reverify_days=30`)을 넘긴 object는 `quick` 실행에서도 해당 object만 강제 deep rehash 대상에 포함한다(또는 매 run마다 가장 오래 deep 검증되지 않은 object 일부를 재해시하는 rolling deep). 이렇게 모든 object가 N일 내 최소 1회 deep 검증되도록 보장하면서 매 scan 전국 재해시는 피한다. (rebuild·run-validation의 사용 직전 무결성 게이트가 최종 안전망이지만, 정기 deep는 그 사이 손상을 미리 표면화한다.)

## Admin 권한 모델

ADR-049의 admin role gate는 구현 필수다. 현재 admin 라우터에는 애플리케이션 인증 레이어가 없으므로 T-109 구현에서 최소 신원 source를 함께 추가한다.

확정 방식:

1. 신원 source는 trusted reverse proxy 또는 Next.js admin proxy가 주입하는 `X-KTG-Actor`, `X-KTG-Roles` 헤더다.
2. 백엔드는 `KTG_ADMIN_TRUSTED_PROXY_CIDRS` 또는 기존 trusted proxy 설정에 포함된 remote address에서 온 요청만 이 헤더를 신뢰한다. 직접 들어온 외부 요청이 같은 헤더를 보내면 무시하거나 403으로 거부한다.
3. FastAPI dependency `require_role(min_role)`은 `RequestContext(actor, roles, request_id)`를 만들고, destructive/rebuild/activate/hash-update API에 부착한다.
4. 내부 job이나 scheduler가 실행하는 작업은 actor를 `system:<job_kind>`로 기록하고, role은 `system`으로 둔다.
5. `ops.audit_events`에는 actor, roles, request id, 대상 resource id, typed confirmation hash, outcome을 남긴다.
6. `X-KTG-Actor`/`X-KTG-Roles`가 없거나 role 이름이 알 수 없는 값이면 protected API는 기본 `403`이다. bootstrap 편의를 위해 빈 role을 관리자처럼 해석하지 않는다.
7. ADR-037 GeoIP Korea-only gate는 admin role gate보다 앞에서 실행된다. 해외 운영자나 복원 직후 특수 접근이 필요하면 GeoIP allow CIDR 또는 trusted proxy 운영 설정으로 해결하고, T-109 source 관리 API가 GeoIP gate를 우회하는 예외를 만들지 않는다.

권장 role:

| role | 허용 범위 |
|------|-----------|
| `source_file_viewer` | source file/group/match set 조회, 다운로드 |
| `source_file_manager` | upload session 생성, multipart upload, register, soft-delete, revalidate |
| `rebuild_operator` | match set activate, rebuild-db, validation run |
| `destructive_admin` | hard-delete, RustFS object delete, `update_hash_after_verify`, orphaned multipart abort |

typed confirmation은 `destructive_admin` 권한을 대체하지 않는다. 권한이 있는 사용자가 위험 작업을 실행할 때 추가로 요구하는 확인 절차다.

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
      "default_role": "build_required",
      "group_kind": "single_file",
      "expected_file_count": 1,
      "required_in_profiles": ["serving_minimal", "serving_recommended"],
      "accepted_extensions": [".zip"],
      "expected_members": ["rnaddrkor_*.txt", "jibun_rnaddrkor_*.txt"],
      "can_infer_yyyymm": true
    }
  ]
}
```

catalog의 `role`/`default_role`은 UI 기본 표시값이다. 최종 권위는 `ops.source_match_set_items.role`이다. 예를 들어 `roadaddr_building_shape_bundle`은 기본 `validation_optional`로 제안되지만, 후속 ADR에서 feature flag 기반 보강 원천으로 승격하면 특정 match set item에서 `enrichment_candidate`로 저장할 수 있다.

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
  "storage_kind": "rustfs",
  "upload_strategy": "multipart"
}
```

응답:

```json
{
  "upload_session_id": "source_upload_...",
  "source_file_group_id": "uuid",
  "category": "roadname_hangul_full",
  "group_kind": "single_file",
  "expected_file_count": 1,
  "user_yyyymm": "202605",
  "state": "created",
  "max_bytes": 2147483648,
  "upload_strategy": "multipart",
  "part_size_bytes": 67108864,
  "registration_state": "not_registered",
  "file_slots": [
    { "slot": "archive", "required": true, "uploaded": false }
  ]
}
```

`user_yyyymm`은 업로드 세션 생성 시 필수다. UI는 파일명/내부 member에서 `YYYYMM` 또는 `YYMM`을 추정할 수 있으면 그 값을 입력 필드의 사전 입력값으로 넣고, 추정할 수 없으면 현재 날짜 기준 `YYYYMM`을 사전 입력값으로 넣는다. 이 값은 자동 확정값이 아니라 사용자가 확인할 제안안이다. 어떤 경우에도 request에는 사용자가 직접 확인·입력한 값만 들어간다. `user_yyyymm`이 없으면 upload session 생성과 RustFS 저장을 모두 거부하며, 백엔드는 누락값을 파일명이나 현재 날짜로 보완하지 않는다.

세션 생성은 `category + user_yyyymm` 기준 advisory lock으로 직렬화한다. 같은 조합의 non-terminal session이 이미 있으면 기본 응답은 `409 Conflict`이며, 응답 body에 기존 `upload_session_id`, state, uploaded slot 수, 재개 가능한 action을 포함한다. 운영자가 새 세션을 강제로 만들려면 기존 session을 cancel/expire 처리하거나, UI에서 "기존 세션을 폐기하고 새 세션 생성" typed confirmation을 거쳐야 한다. 이 규칙은 두 탭이나 두 운영자가 같은 월/카테고리를 동시에 올려 중복 group과 대용량 orphan object를 만드는 일을 막기 위한 것이다.

`multi_part` category의 응답은 `file_slots`에 part 목록을 내려준다. 시도별 자료는 시도 코드 17개를 `part_key`로 내려주며, 사용자는 각 slot에 해당 시도 ZIP을 하나씩 올린다. session validate는 모든 required part가 채워졌는지 coverage를 먼저 확인한다.

```json
{
  "upload_session_id": "source_upload_...",
  "source_file_group_id": "uuid",
  "category": "electronic_map_full",
  "group_kind": "multi_part",
  "expected_file_count": 17,
  "user_yyyymm": "202604",
  "state": "created",
  "max_bytes": 2147483648,
  "upload_strategy": "multipart",
  "part_size_bytes": 67108864,
  "registration_state": "not_registered",
  "file_slots": [
    { "part_kind": "sido", "part_key": "11", "part_label": "서울특별시", "required": true, "uploaded": false },
    { "part_kind": "sido", "part_key": "41", "part_label": "경기도", "required": true, "uploaded": false }
  ]
}
```

`max_bytes=2147483648`은 현행 `api_max_upload_bytes` 기본값 예시다. 2026-06-14 리뷰 기준으로 SHP 3종은 묶음 ZIP을 만들지 않고 시도별 ZIP을 개별 업로드하므로, 현재 확인된 단일 업로드 파일은 2GiB 한계에 걸리지 않는다. 그래도 1차 구현의 정식 업로드 경로는 multipart/resumable이다. 단일 PUT은 테스트 fixture나 내부 fallback에만 허용한다.

### 업로드 세션 목록/재개

```text
GET /v1/admin/source-files/upload-sessions?state=&category=&user_yyyymm=&created_by=
GET /v1/admin/source-files/upload-sessions/{upload_session_id}
```

목록 API는 진행 중 세션을 다시 찾는 공식 진입점이다. 사용자가 브라우저를 닫거나 다음날 이어 올리는 시나리오를 위해 `created`, `uploading`, `uploaded_to_temp`, `storing_to_rustfs`, `awaiting_registration`, 그리고 `failed_register`/`failed_storage_state` 같은 재개·재업로드로 복구 가능한 실패 상태를 필터링할 수 있어야 한다. 응답은 session별 uploaded slot 수, 남은 required part, `multipart_upload_id`, `registration_deadline_at`, 마지막 오류, 재개 가능한 action을 포함한다.

Admin UI는 `/admin/source-files` 첫 화면에 "재개 가능한 업로드" 목록을 노출한다. 사용자가 `upload_session_id`를 따로 기록하지 않아도 같은 category/기준년월 세션을 찾아 이어 올릴 수 있어야 한다.

### 파일 업로드

```text
POST   /v1/admin/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart
PUT    /v1/admin/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart/{part_number}
POST   /v1/admin/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart/complete
DELETE /v1/admin/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/multipart
POST   /v1/admin/source-files/upload-sessions/{upload_session_id}/files/{slot_id}/replace
```

`single_file`은 `slot_id='archive'` 하나만 채우고, `multi_part`는 `part_key`로 각 slot을 채운다. 서버가 파일명에서 시도명이나 part 이름을 추론할 수 있더라도 최종 slot 배정은 사용자가 선택한 category와 slot이 우선한다. 각 part 업로드 응답은 part number, received bytes, part etag/checksum을 반환하고, complete 단계에서 전체 SHA-256 계산과 RustFS object head 검증을 실행한다.

브라우저는 `XMLHttpRequest.upload.onprogress` 또는 동등한 wrapper를 써서 byte percent를 표시한다. 서버도 `uploaded_bytes`, `total_bytes`를 기록하지만 브라우저 progress가 1차 표시 기준이다.

multi-part lifecycle:

- `register` 전에는 실패한 part를 abort 후 재업로드할 수 있고, 이미 완료된 slot도 `replace`로 명시 교체할 수 있다. `replace`는 기존 slot object를 `superseded` metadata로 표시하거나 multipart abort/delete를 시도하고, 해당 session의 구조 검증 결과와 hash 결과를 무효화한 뒤 새 파일을 받는다.
- `register` 후에는 group 전체 재등록을 기본 복구 경로로 둔다. 단, `multi_part` group의 일부 part만 파일이 손상되거나 누락된 운영 복구 케이스를 위해 `replace_part` API를 후속 구현 후보로 남기되, replace가 끝나면 같은 transaction에서 `recompute_group_aggregates()`와 참조 match set invalidation을 실행해야 한다.
- 이미 `available`인 group에 part를 추가해 expected coverage를 바꾸는 경로는 금지한다. coverage 구조가 바뀌면 새 group을 만들어 새 match set에서 선택한다.

### 검증 시작/상태 조회

```text
POST /v1/admin/source-files/upload-sessions/{upload_session_id}/validate
GET  /v1/admin/source-files/upload-sessions/{upload_session_id}
GET  /v1/admin/source-files/upload-sessions/{upload_session_id}/events
```

검증은 upload 완료 후 별도 시작할 수 있게 한다. UI는 업로드 완료와 검증 실패를 분리해서 보여준다.

`events`는 기존 `/v1/admin/jobs/{job_id}/events`와 같은 SSE 패턴을 따른다. event data는 최소 다음 필드를 가진다.

```json
{
  "event": "source_upload.progress",
  "upload_session_id": "source_upload_...",
  "state": "validating_structure",
  "stage": "validate:electronic_map_full",
  "progress": 0.42,
  "current_item": "서울특별시.zip/TL_SPBD_BULD.dbf",
  "uploaded_bytes": 123,
  "total_bytes": 456,
  "message": "전자지도 layer sidecar를 확인하는 중",
  "log_tail": "..."
}
```

terminal state는 `available`, `quarantined`, `failed_*`, `cancelled`, `expired` 중 하나다. 클라이언트는 SSE가 끊기면 `GET /v1/admin/source-files/upload-sessions/{id}` polling으로 fallback한다.

### Registry 등록 승인

```text
POST /v1/admin/source-files/upload-sessions/{upload_session_id}/register
```

요청:

```json
{
  "confirm_user_yyyymm": "202605",
  "display_name": "202605 도로명주소 한글 전체분",
  "yyyymm_mismatch_ack": true,
  "registration_note": "내부 파일 기준월 202605를 기준으로 등록"
}
```

`confirm_user_yyyymm`은 upload session의 `user_yyyymm`과 같아야 한다. 서버는 이 값을 기준년월 수정 요청으로 해석하지 않는다. 파일명/내부 member에서 추정한 기준월과 다르면 `yyyymm_mismatch_ack=true`를 요구하고, mismatch 근거와 사용자의 승인 여부를 audit event에 남긴다.

성공 응답:

```json
{
  "source_file_group_id": "uuid",
  "category": "roadname_hangul_full",
  "group_kind": "single_file",
  "state": "available",
  "user_yyyymm": "202605",
  "group_sha256": "...",
  "files": [
    {
      "source_file_id": "uuid",
      "original_filename": "202605_도로명주소 한글_전체분.zip",
      "sha256": "...",
      "size_bytes": 123,
      "storage_uri": "rustfs://..."
    }
  ]
}
```

`register`는 다음을 원자적으로 처리해야 한다. 여기서 "원자적"은 사용자에게 보이는 registry 상태가 일관되게 전환된다는 뜻이며, RustFS와 PostgreSQL 사이의 실제 분산 트랜잭션을 뜻하지 않는다.

1. group의 모든 required file slot 업로드 여부 확인
2. upload streaming 단계에서 계산해 session에 저장한 각 archive SHA-256, size, part etag/checksum 존재 여부 확인
3. file 단위 duplicate detection과 group 단위 `group_sha256` 계산. `group_sha256`은 child `(part_kind, part_key, sha256, size_bytes)` metadata로만 계산하고 archive 본문을 다시 읽지 않는다.
4. 사용자가 입력한 `user_yyyymm`과 inferred yyyymm mismatch 확인. mismatch가 있으면 `yyyymm_mismatch_ack=true`가 필요하다.
5. RustFS head 검증. `head_object`로 size/etag/metadata를 확인하고, head 값이 upload session 기록과 다르거나 검증 이력이 없을 때만 object를 다시 읽어 SHA-256을 재계산한다.
6. `ops.source_file_groups` insert/update
7. `ops.source_files` insert
8. `ops.source_file_members` insert
9. audit event 기록

RustFS 저장은 `register` 전에 이미 완료되어 있어야 한다. DB insert 실패 시 object는 "미등록 저장 object"로 남고, 사용자는 같은 upload session의 `register`를 재시도할 수 있다. upload session 정보가 사라진 뒤에도 reconciliation이 object metadata와 key를 스캔해 `object_missing_db`로 노출하고, 사용자가 category와 `user_yyyymm`을 확인해 registry import를 재시도할 수 있다. DB insert 성공 후 object 확인 실패 시 `source_files.state='missing'` 또는 `quarantined`로 남긴다.

동시성 규칙:

- 모든 `advisory lock` 표기는 PostgreSQL advisory lock을 뜻한다. Python process lock이나 row-level lock으로 대체하지 않는다.
- 같은 `category + user_yyyymm + group_sha256` register는 PostgreSQL advisory lock으로 직렬화한다. file 단위 중복은 child `sha256 + size_bytes + part_kind + part_key`로 warning을 만든다.
- 같은 `bucket + object_key`는 unique index와 object head preflight로 중복 put을 막는다.
- `ops.source_match_sets.state='active'`는 partial unique index로 한 건만 허용한다.
- 미등록 stored object는 reconciliation 대상이며, 운영 SLA는 "다음 정기 reconciliation 또는 수동 scan에서 import/delete 후보로 노출"로 둔다.

권장 lock key namespace:

| lock key | 보호 대상 |
|----------|-----------|
| `source_upload_session:{category}:{user_yyyymm}` | 같은 category/month의 진행 중 upload session 1개 제한 |
| `source_register:{category}:{user_yyyymm}:{group_sha256}` | storage-first register 중복 방지 |
| `source_match_activate` | active match set atomic swap과 rollback one-active invariant |
| `source_rebuild_db` | rebuild-db, legacy full_load_batch, mv_refresh, restore hot-swap 직렬화 |
| `source_janitor` | upload session 만료 처리와 multipart abort 중복 실행 방지 |

### 파일 목록/다운로드/삭제

```text
GET  /v1/admin/source-file-groups?category=&yyyymm=&state=
GET  /v1/admin/source-file-groups/{source_file_group_id}
POST /v1/admin/source-file-groups/{source_file_group_id}/soft-delete
POST /v1/admin/source-file-groups/{source_file_group_id}/hard-delete
POST /v1/admin/source-file-groups/{source_file_group_id}/restore
POST /v1/admin/source-file-groups/{source_file_group_id}/revalidate
GET  /v1/admin/source-files?source_file_group_id=&part_kind=&part_key=&state=
GET  /v1/admin/source-files/{source_file_id}
GET  /v1/admin/source-files/{source_file_id}/download
POST /v1/admin/source-files/{source_file_id}/soft-delete
POST /v1/admin/source-files/{source_file_id}/hard-delete
POST /v1/admin/source-files/{source_file_id}/restore
POST /v1/admin/source-files/{source_file_id}/revalidate
```

삭제 원칙:

- 목록에서 row를 바로 삭제하지 않는다.
- group `soft-delete`는 match set에서 새로 선택되지 않게 하되 감사 row와 RustFS object를 보존한다. child file도 함께 `soft_deleted`로 전환한다.
- `restore`는 `soft_deleted` row만 대상으로 한다. 서버는 RustFS `head_object`와 SHA-256/size 검증을 먼저 수행하고, object가 있으면 `state='validating'`으로 되돌린 뒤 `revalidate`를 실행한다. 검증이 `passed` 또는 `warning`이면 `available`, 실패하면 `quarantined`, object가 없으면 `missing`으로 남긴다. 복구 후 `deleted_at=NULL`로 갱신하고 `recompute_group_aggregates()`를 호출해 참조 match set을 `revalidatable` 또는 `integrity_alert` 해제 후보로 전파한다.
- group `hard-delete`는 typed confirmation을 요구하고 child RustFS object 삭제를 모두 시도한다. 일부 삭제 실패 시 group은 `quarantined`, 실패 child file은 `delete_failed` 또는 `quarantined`로 남긴다.
- file 단위 삭제는 `multi_part`의 일부 part 파일만 보정해야 하는 운영 복구용이다. 일반 UI는 group 단위 삭제를 기본으로 한다.
- 이미 active release/match set이 참조하는 group은 hard delete를 막고, 먼저 match set을 retire하도록 요구한다.

hard-delete, `update_hash_after_verify`, `delete_object`, match set `activate`, `rebuild-db`는 파괴적이거나 고권한 작업이다. T-109 구현은 admin role gate를 필수로 도입해 read-only viewer, source-file manager, rebuild operator, destructive admin 권한을 분리한다. typed confirmation은 role gate를 대체하지 않고, destructive admin 권한이 있는 사용자가 위험 작업을 실행할 때 추가로 요구하는 안전장치다. `ops.audit_events`에는 actor, role, request id, 대상 resource id, typed confirmation hash, outcome을 남긴다.

### RustFS 정합성 검증

```text
POST /v1/admin/source-files/reconcile
GET  /v1/admin/source-files/reconcile/{source_storage_reconcile_run_id}
GET  /v1/admin/source-files/reconcile/{source_storage_reconcile_run_id}/items
POST /v1/admin/source-files/reconcile/items/{source_storage_reconcile_item_id}/resolve
```

resolve action 예:

```json
{ "action": "mark_db_missing" }
{ "action": "soft_delete_db_row" }
{ "action": "restore_soft_deleted" }
{ "action": "import_object", "category": "locsum_full", "user_yyyymm": "202604" }
{ "action": "delete_object" }
{ "action": "extend_registration_deadline", "registration_deadline_at": "2026-07-31T00:00:00Z" }
{ "action": "retry_delete_object" }
{ "action": "update_hash_after_verify", "typed_confirmation": "현재 RustFS object를 정본으로 인정" }
```

미등록 object import는 다음 단계로 수행한다.

1. `list_objects(prefix)`로 key/size/etag 후보를 수집한다.
2. DB에 없는 key에 대해서만 `head_object`를 호출해 metadata를 읽는다.
3. metadata가 없거나 불완전하면 object key의 `<category>/<user_yyyymm>/<group>/<file>/<part_key>` 구조를 파싱해 후보값을 채운다.
4. upload session이 살아 있고 `registration_deadline_at` 전이면 `pending_registration`으로 분류하고 import/delete 후보에서 제외한다.
5. upload session은 살아 있지만 deadline이 지났거나 session metadata만 남아 있으면 `registration_expired`로 분류한다. 자동 삭제하지 않고, registry 등록 재시도, deadline 연장, 세션 폐기 후 object delete를 UI에서 고르게 한다.
6. 사용자가 category, `user_yyyymm`, part 정보를 확인한 뒤 registry import 또는 object delete를 선택한다.
7. resolve 직전에는 DB row와 RustFS head를 다시 읽어 동시 register/delete로 인한 오탐을 제거한다. `duplicate_object` resolve는 active match set이 참조하는 object(`integrity_alert` 값과 무관)와 draft/validated match set이 참조하는 정본 object를 삭제 대상으로 고를 수 없다.

## Match set API 설계

### 생성/수정

```text
POST /v1/admin/source-match-sets
PATCH /v1/admin/source-match-sets/{source_match_set_id}
POST /v1/admin/source-match-sets/{source_match_set_id}/items
DELETE /v1/admin/source-match-sets/{source_match_set_id}/items/{source_match_set_item_id}
POST /v1/admin/source-match-sets/{source_match_set_id}/validate
POST /v1/admin/source-match-sets/{source_match_set_id}/activate
POST /v1/admin/source-match-sets/{source_match_set_id}/retire
```

`POST /validate`는 입력 state별로 동작을 분리한다. `draft`는 canonical hash와 coverage를 산출해 `validated`로 전이하고, `revalidatable`은 hash/coverage를 재검산해 이전 usable state(`validated`)로 복구한다. `active`는 `integrity_alert=true`인 경우에만 validate-in-place를 허용하며, 성공해도 `state='active'`를 유지하고 `integrity_alert`만 해제한다. `retired`, `invalid`, `restored_from_backup`은 직접 validate 대상이 아니다(`invalid`와 `restored_from_backup`은 먼저 `revalidatable` 전이를 거쳐야 한다).

생성 요청 예:

```json
{
  "name": "202605 도로명주소 + 202604 전자지도 권장 조합",
  "profile": "serving_recommended",
  "items": [
    { "category": "roadname_hangul_full", "source_file_group_id": "...", "role": "build_required" },
    { "category": "locsum_full", "source_file_group_id": "...", "role": "build_required" },
    { "category": "navi_full", "source_file_group_id": "...", "role": "build_required" },
    { "category": "electronic_map_full", "source_file_group_id": "...", "role": "build_required" },
    { "category": "roadaddr_entrance_full", "source_file_group_id": "...", "role": "build_recommended" },
    { "category": "zone_shape_full", "source_file_group_id": "...", "role": "build_recommended" },
    { "category": "national_point_grid_center", "omitted": true, "omitted_reason": "미보유", "role": "validation_optional" }
  ]
}
```

검증 규칙:

- profile 필수 category가 빠지면 `validate` 실패.
- optional category는 `source_file_group_id` 또는 `omitted=true` 중 하나를 반드시 가져야 한다.
- 참조 group이 `available`이 아니면 실패.
- `roadaddr_entrance_full.user_yyyymm`이 `roadname_hangul_full.user_yyyymm`과 다르면 "direct 출입구 좌표 승격 제한" warning.
- `zone_shape_full` 기준월이 다른 것은 허용하되 C10 note에 남긴다.
- `mixed_yyyymm=true`인 match set은 자동 활성화하지 않는다. 사용자가 category별 기준월 표를 확인하고 typed acknowledgement를 남기면 activate 또는 rebuild를 진행할 수 있다.
- 같은 category는 match set 안에서 group 하나만 참조한다. 시도별 17개 archive 같은 multi-part 자료는 group 내부 child file로 표현하고, item을 여러 개 만들지 않는다.

활성화 규칙:

- `POST /activate`는 `validated` 상태에서만 허용한다.
- 기존 active match set을 먼저 `retired`로 바꾸고 새 match set을 `active`로 바꾸는 작업은 한 transaction 안에서 수행한다.
- 같은 `source_set_hash`가 이미 active release에 연결되어 있으면 기본 응답은 "이미 같은 원천 조합으로 구성됨" warning이다. 강제 재적재는 별도 typed confirmation을 요구한다.
- rollback으로 이전 serving release를 되돌릴 때도 current source 표시는 release의 `dataset_snapshot_id -> source_match_set_id` 경로를 따른다. rollback 대상 snapshot이 T-109 match set FK를 갖고 있으면 기존 active match set을 `retired`로 내리고 대상 match set을 `active`로 복원하는 atomic swap을 수행한다. rollback 직전 source quick reconcile로 대상의 `integrity_alert`를 재계산한다. rollback 대상 snapshot이 legacy라 FK가 없으면 `알수없음`과 `추정` 배지를 사용하고, legacy 추정값을 정본 match set으로 승격하지 않는다.

### DB 재구성

```text
POST /v1/admin/source-match-sets/{source_match_set_id}/rebuild-db
```

이 API는 기존 `full_load_batch`를 대체하지 않고, match set에서 `build_full_load_source_set_plan`과 같은 형태의 batch payload를 조립해 기존 queue를 호출한다. `SourceSetPlan.batch_payload`는 조립 결과를 담는 DTO field로만 표현한다.

처리 흐름:

1. match set validate (참조 group이 모두 `available`이고 `group_sha256 IS NOT NULL`인 DB 상태 확인)
2. 선택된 RustFS archive를 temp/materialized 작업 디렉터리로 다운로드. download는 `download_concurrency` 기본 3, 저사양 장비에서는 1로 조정 가능하게 한다.
3. **적재 전 무결성 게이트.** 다운로드한 각 part archive의 SHA-256/size를 registry의 child `ops.source_files.sha256`/`size_bytes`와, group 전체를 `group_sha256`와 대조한다. 업로드(`register`)와 rebuild 사이에는 시간차(며칠~몇 주)가 있어 그동안 RustFS object가 사용자/외부에 의해 교체·손상·삭제될 수 있으므로, reconciliation의 정기 full 재해시와 **별개로** rebuild가 자체 재대조해야 한다. 구현은 다운로드 streaming 중 SHA-256을 계산해 별도 재읽기를 피하되, `full_load_batch` child를 enqueue하기 직전 이 게이트 결과가 모두 `passed`인지 다시 확인한다. 하나라도 불일치/누락이면 rebuild를 **중단**하고, 해당 file/group을 `quarantined`로 전환한 뒤 `recompute_group_aggregates()`로 참조 match set에 전파한다. active match set은 `state='active'` 유지 + `integrity_alert=true`, 비-active `validated` match set은 `invalid`로 전환하고(`draft`/`restored_from_backup` pre-hash는 유지) 사용자를 reconciliation으로 유도한다(부분 적재된 상태는 만들지 않는다).
4. 다운로드·무결성 검증이 끝난 part부터 즉시 압축 해제하는 producer/consumer 파이프라인을 사용한다. `materialize_concurrency` 기본 2~3, DB COPY 단계와는 분리한다.
5. 기존 loader가 기대하는 path로 materialize한다. peak disk는 "N개 동시 download/extract 분량 + loader input"을 넘지 않도록, extract 완료 뒤 임시 archive를 삭제할 수 있는 category는 즉시 제거한다.
6. `full_load_batch` children 생성
7. root payload에 `source_match_set_id`, category별 `source_file_group_id`, child `source_file_id` 목록, `user_yyyymm`, `group_sha256`, `storage_uri`를 남김
8. DB 적재/COPY와 MV refresh는 기존 JobQueue 직렬 실행 규칙을 유지한다. 다운로드·해제 병렬화가 DB write 병렬화로 번지면 안 된다.
9. load 완료 후 consistency check와 MV refresh
10. `ops.dataset_snapshots.source_match_set_id` FK를 정본으로 기록한다. `ops.dataset_snapshots.source_set` JSONB에는 동일 내용을 read-only snapshot으로 남길 수 있지만 정본으로 쓰지 않는다. `ops.serving_releases`는 `dataset_snapshot_id`를 통해 snapshot을 경유해 match set을 조회하며 직접 match set 컬럼을 갖지 않는다.

동시성·중단·승격 규칙:

- `rebuild-db`는 legacy `full_load_batch`, `mv_refresh`, restore hot-swap과 같은 전역 advisory lock을 공유한다. 두 운영자가 동시에 rebuild를 눌러도 하나만 진행하고 나머지는 `409` 또는 "이미 실행 중" 상태를 반환한다.
- rebuild 시작 시 같은 match set 또는 같은 staging key의 `running` job이 heartbeat timeout을 넘겼으면 새 작업을 시작하기 전에 이전 job을 `failed`로 강제 마감하고 staging/materialized 디렉터리를 멱등하게 재초기화한다.
- 실제 적재는 swap 전 staging/shadow 구조에서만 수행한다. 프로세스가 loader/COPY 도중 죽으면 active match set과 active release는 그대로 유지하고, 새 snapshot/release를 만들지 않는다.
- consistency `severity_max='ERROR'`이면 MV swap, active 승격, `ops.dataset_snapshots.source_match_set_id` 기록을 모두 차단하고 rebuild job을 failed로 끝낸다. WARN/INFO/OK는 자동 승격 대상이다.
- 이미 알려진 원천 품질 ERROR를 운영자가 받아들이는 예외 경로는 `destructive_admin` role과 typed confirmation을 요구한다. 이 경우 report와 snapshot metadata에 `forced_promotion=true`, 승인 actor, 사유, case 목록을 기록한다. `forced_promotion=true`는 consistency ERROR 승격 차단만 우회한다. 적재 전 source archive integrity gate(hash/size/object presence), `source_file_group.state!='available'`, selected match set의 `integrity_alert=true`는 우회하지 못하며, 이 경우 rebuild는 snapshot/release를 만들지 않고 실패해야 한다.
- `run-validation`은 rebuild와 같은 lock을 공유하거나, 최소한 시작 시점의 active `dataset_snapshot_id`를 pin해서 rebuild 도중 바뀐 snapshot과 섞이지 않게 한다.

> 같은 무결성 원칙은 RustFS에서 archive를 받아 적재·검증에 쓰는 모든 흐름에 적용한다. 아래 `run-validation`도 optional 검증 자료를 materialize하기 전에 동일하게 registry hash와 대조하고, 불일치 시 해당 검증 입력을 `skipped`가 아니라 `failed`로 기록한다.

### 기존 DB에 검증 자료 추가 후 검증

```text
POST /v1/admin/source-match-sets/{source_match_set_id}/run-validation
```

이 API는 새 DB를 만들지 않고 optional validation category만 materialize해서 validation job을 실행한다.

요구사항:

- active release 또는 사용자가 고른 snapshot/match set 기준으로 실행한다.
- optional 자료가 없으면 `skipped=true`를 report에 남긴다.
- optional 자료가 있으면 materialize 직후와 validator 실행 직전 archive SHA-256/size를 registry와 대조한다. 불일치/누락은 `skipped`가 아니라 `failed`이며, `validation_inputs.<category>.state='failed'`, `failure_reason='source_integrity_mismatch'`를 남긴다. 새 DB 적재나 snapshot/release 생성은 하지 않고, 해당 group은 `quarantined`로 전환한다. 참조 match set 전파는 공통 규칙을 따른다(active는 `integrity_alert=true`, 비-active `validated`는 `invalid`, `draft`/`restored_from_backup` pre-hash는 유지).
- 새 케이스가 생기면 C11부터 번호를 붙이고 UI 탭에 표시한다.
- validation 결과는 `load_consistency_reports.source_set` 또는 별도 `validation_inputs`에 어떤 optional 자료가 있었고 무엇이 생략됐는지 기록한다.

## 운영 시나리오 커버리지 점검

PR #131 추가 코멘트를 반영한 뒤, 구현자가 빠뜨리기 쉬운 분기를 다음 표로 고정한다. 결론은 **핵심 시나리오 누락은 닫혔고**, 구현 PR은 아래 운영 복구·정리 경로까지 테스트·API 응답·UI 상태로 추적 가능하게 만들어야 한다.

| 영역 | 시나리오 | 필수 동작 |
|------|----------|-----------|
| 업로드 세션 생성 | `user_yyyymm`이 없거나 빈 문자열 | 백엔드는 세션을 만들지 않고 `400` 계열 오류를 반환한다. 파일명 추정값이나 현재 `YYYYMM`은 서버 fallback이 아니라 UI 사전 입력값일 뿐이다. |
| 업로드 세션 생성 | 파일명/상위 디렉터리/내부 member에서 추정한 기준월이 사용자가 입력한 값과 다름 | 저장은 허용하되 mismatch warning, 추론 근거, 사용자가 확정한 `user_yyyymm`을 audit에 남긴다. 자동 보정하지 않는다. |
| 업로드 세션 생성 | 같은 `category + user_yyyymm`의 진행 중 session이 이미 있음 | 새 session을 만들지 않고 `409`와 기존 session 요약을 반환한다. 사용자는 기존 session 재개, cancel/expire, typed confirmation 기반 새 session 생성 중 선택한다. |
| 업로드 진행 | multipart upload가 중단됐다가 재개됨 | `ops.source_upload_sessions`와 `ops.source_upload_session_parts`의 part checksum/etag로 이어 올리고, 같은 part 재전송은 idempotent하게 처리한다. |
| 업로드 진행 | DB에는 multipart part 기록이 있지만 RustFS multipart upload id가 이미 abort/expire됨 | 재개 시 RustFS `ListParts` 또는 호환 API로 storage 상태를 먼저 확인한다. upload id가 없으면 session을 `failed_storage_state`로 전환하고 해당 slot을 새 multipart upload로 다시 올리게 한다. |
| 업로드 진행 | 사용자가 `upload_session_id`를 기억하지 못함 | `GET /upload-sessions` 목록과 UI "재개 가능한 업로드"에서 category, 기준월, 진행률로 다시 찾을 수 있어야 한다. |
| 업로드 진행 | 완료된 slot에 잘못된 파일을 올린 것을 register 전에 발견함 | `replace` API로 해당 slot을 명시 교체한다. 기존 검증/hash 결과를 무효화하고 새 파일 검증을 다시 요구한다. |
| 업로드 진행 | 사용자가 upload를 취소하거나 네트워크 실패로 partial object가 남음 | multipart abort를 우선 실행하고, 남은 임시 object는 일반 source prefix가 아니라 reconciliation의 `orphaned_multipart` 또는 미등록 object 후보로만 노출한다. |
| 업로드 진행 | RustFS 저장은 끝났지만 사용자가 registry 등록을 며칠 뒤로 미룸 | `registration_deadline_at` 전에는 reconciliation에서 `pending_registration`으로 분류해 삭제 후보로 취급하지 않는다. |
| 업로드 진행 | `expires_at` 또는 `registration_deadline_at`이 지남 | PostgreSQL advisory lock 기반 janitor가 미완 multipart를 abort하고 session을 `expired`로 마감한다. 저장 완료 object는 삭제하지 않고 `registration_expired` issue로 전환한다. |
| 구조 검증 | 사용자가 고른 category와 archive 내부 구조가 다름 | registry row를 만들지 않는다. 사용자가 보존을 선택한 경우에만 `quarantined` 등록 후보로 남기고, match set 선택은 막는다. |
| epost server-fetch | epost 서버 fetch 실패(사이트 다운, 인증서 만료, HTML/다운로드 URL 구조 변경) | source registry row를 만들지 않고 fetch session을 failed로 마감한다. 자동 polling/retry loop는 두지 않으며, 운영자가 설정 또는 URL을 수정한 뒤 수동 재시도한다. |
| epost server-fetch | fetch 후 pobox/bulk ZIP 구조가 loader 기대 member와 불일치 | RustFS 저장은 보존할 수 있지만 기본 registry 등록은 막고, 사용자가 보존을 택한 경우에만 `quarantined` 후보로 남긴다. `pobox_load`/`bulk_load`는 실행하지 않는다. |
| epost server-fetch | epost `user_yyyymm`이 현재 serving 기준월 또는 최신 source set과 다름 | 핵심 rebuild와 독립이므로 hard error는 아니다. mismatch warning과 user-confirmed `user_yyyymm`을 audit/report에 남기고, 우편번호 검증 report에 기준월 차이를 표시한다. |
| Registry 등록 | RustFS 저장·검증은 끝났지만 DB insert가 실패함 | `failed_register` 상태로 남기고 같은 upload session에서 register를 재시도한다. storage-first 구조이므로 object를 자동 삭제하지 않는다. |
| Registry 등록 | 동일 SHA-256/size archive가 이미 있음 | hard error가 아니라 중복 후보 warning을 보여준다. 사용자는 기존 group 재사용, 새 group 등록, 취소 중 선택한다. |
| Multi-part group | 17개 시도 ZIP 중 일부가 누락됐거나 같은 `part_key`가 중복됨 | `recompute_group_aggregates()`가 `source_file_group_incomplete`를 계산하고 match set validate를 실패시킨다. 중복 part는 명시 교체 또는 세션 재생성 없이는 등록하지 않는다. |
| RustFS 직접 변경 | DB row는 있는데 object가 삭제됨 | reconciliation에서 `db_missing_object`를 만들고 file/group을 `missing` 또는 `quarantined`로 전환한다. rebuild와 run-validation은 시작 전 또는 materialize 중 동일하게 중단한다. |
| RustFS 직접 변경 | DB에는 없지만 object가 prefix에 직접 추가됨 | reconciliation에서 `object_missing_db`를 만들고, 사용자가 import/delete를 선택한다. import 시에도 category, `user_yyyymm`, 구조 검증, SHA-256 계산을 다시 거친다. |
| RustFS 직접 변경 | object size/etag/SHA-256이 registry와 다름 | quick scan은 size/etag 변화로 의심 항목을 만들고, deep scan 또는 사용 직전 gate는 streaming rehash로 mismatch를 확정한다. 확정 후 hash 자동 갱신은 금지하고 typed confirmation이 있는 `update_hash_after_verify`만 허용한다. same-size/etag 변조 안전망으로 `last_deep_verified_at` 경과 object는 quick에서도 강제 deep 대상이다. |
| RustFS 직접 변경 | bucket 전체가 삭제되거나 prefix 대량 손상됨 | serving DB는 즉시 장애로 보지 않지만, registry 기준 모든 누락 object를 `db_missing_object`/`source_file_unavailable`로 표시한다. active match set은 `integrity_alert=true`, 비-active `validated`는 `invalid`로 전파하고, 복구는 원천 재업로드/재연결 -> group revalidate -> match set validate/activate 순서로 진행한다. |
| 파일 복구 | `soft_deleted` group/file을 되살림 | `restore`가 RustFS head/hash를 확인한 뒤 `validating -> available` 또는 `quarantined/missing`으로 전이한다. `deleted_at`을 비우고 match set 전파를 다시 계산한다. |
| Match set 구성 | 필수 category가 빠졌거나 `available`이 아닌 group을 참조함 | `validate` 실패. optional category만 `omitted=true`와 `omitted_reason`으로 생략할 수 있다. |
| Match set 활성화 | `source_set_hash`가 stale이거나 item이 바뀜 | `activate` 직전 canonical hash를 다시 계산한다. DB의 `source_set_hash`와 다르면 활성화하지 않고 재검증을 요구한다. |
| Match set 활성화 | 이미 active match set이 있는 상태에서 새 match set activate | advisory lock + 단일 transaction에서 기존 active를 `retired`로 바꾼 뒤 새 match set을 `active`로 만드는 atomic swap을 수행한다. **외부에서 관찰 가능한 active gap(0건)이나 unique 위반**을 만들지 않는다(transaction 내부 순간 상태는 무관). |
| Match set 복구 | active match set이 참조하는 object가 손실됨 | active는 `state='active'` 유지 + `integrity_alert=true`(serving 장애 아님, 재구성 가능성 결손). group이 모두 `available`이 되면 `POST /validate` active validate-in-place 성공 시 `integrity_alert=false`로 복구한다. 비-active는 `invalid`→`revalidatable`→`validate`→`validated` 경로. |
| Match set 복구 | 비-active `invalid` match set의 모든 group이 복구됨 | `recompute_group_aggregates()`가 참조 match set을 `revalidatable`로 올린다. 자동 active 승격은 없고 사용자가 `validate`를 실행해야 한다. |
| DB 재구성 | RustFS object가 register 이후 교체·손상됐지만 reconciliation이 아직 돌지 않음 | rebuild job이 다운로드/materialize 중 계산한 SHA-256/size를 loader enqueue 직전 재확인한다. mismatch면 child job을 만들지 않고 group `quarantined`, active match set은 `integrity_alert=true`, 비-active `validated` match set은 `invalid`(pre-hash는 유지), audit event를 남긴다. |
| DB 재구성 | archive integrity는 맞지만 압축 해제/materialize가 실패함 | load job은 `failed`가 되고 temp 디렉터리를 정리한다. source registry와 match set은 자동 invalidation하지 않으며, snapshot/release는 생성하지 않는다. |
| DB 재구성 | loader/COPY 도중 API 프로세스가 죽음 | stale running job을 heartbeat timeout으로 failed 처리하고 staging/materialized 디렉터리를 재초기화한다. active match set/release는 유지하고 snapshot은 만들지 않는다. |
| DB 재구성 | loader/COPY 또는 consistency가 실패함 | 기존 load job 실패 규칙을 따른다. source registry는 입력 무결성이 맞았으므로 유지하고, `ops.dataset_snapshots.source_match_set_id`와 active release는 성공 전까지 갱신하지 않는다. |
| DB 재구성 | consistency `severity_max=ERROR` | MV swap, active 승격, snapshot FK 기록을 차단한다. 알려진 원천 품질 ERROR만 `destructive_admin` typed confirmation으로 `forced_promotion=true`를 남기고 강제 승격할 수 있다. 단 source archive integrity gate와 selected match set `integrity_alert`은 forced promotion으로 우회할 수 없다. |
| 사후 검증 | optional validation 자료가 match set에 없음 | 해당 case는 `skipped`로 기록한다. 성공으로 간주하지 않고 UI/report에서 생략 사유를 표시한다. |
| 사후 검증 | optional validation 자료는 있으나 RustFS object integrity가 깨짐 | `validation_inputs.<category>.state='failed'`로 기록하고 validation job은 failed가 된다. 새 DB 재구성, snapshot 생성, active release 변경은 없다. |
| 사후 검증 | validator version이 바뀌어 기존 `passed` 결과를 신뢰할 수 없음 | 해당 category/group은 `validation_state='not_started'` 또는 `validating` 후보로 되돌리고, 참조 match set은 재검증 필요 상태를 표시한다. |
| 백업/복원 | backup manifest의 `source_match_set_id`가 복원 DB에 없음 | 사용자 승인 후 `restored_from_backup` read-only reconstructed match set을 만들 수 있다. 이 상태는 재구성 입력으로 바로 쓰지 않고, object availability 확인을 거쳐야 한다. |
| 백업/복원 | 빈 DB에 manifest 기반 reconstructed match set을 생성함 | manifest item별 stub group/file을 `missing` 상태로 만들고, items가 그 stub을 참조한다. `restored_from_backup`은 canonical `source_set_hash`가 없을 수 있음을 허용한다. |
| 백업/복원 | manifest에는 source file metadata가 있으나 RustFS object가 현재 bucket에 없음 | UI에 `source_file_unavailable`/`db_missing_object`를 노출한다. DB 백업 archive만으로 원천 archive가 복원됐다고 보지 않는다. |
| 백업/복원 | restore hot-swap 또는 rename 방식으로 운영 DB를 교체함 | hot-swap 직후 source quick reconcile을 1회 자동 실행하고, active snapshot의 `source_match_set_id`와 RustFS object availability를 표시한다. 결손이 있으면 serving은 유지하되 재구성 불가 경고를 띄운다. |
| 백업/복원 | `restored_from_backup` stub에 object를 재연결함 | **두 상태머신을 구분**: group/file은 `missing -> validating -> (storage SHA-256/size 재계산 + 구조 validator passed/warning) -> available`, match set은 (canonical hash 산출 후) `restored_from_backup -> revalidatable -> (validate) -> validated`. `validation_state='unknown'`인 채 `available`로 바꾸지 않고, manifest hash와 재계산 hash가 다르면 `quarantined`/reconcile issue로 보낸다. |
| 복원/운영 접근 | GeoIP gate 때문에 admin API가 403이 됨 | T-109 API는 GeoIP를 우회하지 않는다. 운영자는 trusted proxy/allow CIDR로 접근 경로를 열고, role header가 없으면 protected action은 403이다. |
| 현재 구성 표시 | T-109 도입 전 DB라 match set FK가 없음 | `알수없음`을 표시하고, legacy `source_set` JSONB에서 추정한 값은 `추정` 배지로만 보여준다. 정본 registry로 자동 승격하지 않는다. |
| Admin 권한 | trusted proxy header가 없거나 role이 부족함 | 보호 API는 `403`으로 거부하고 audit에 actor source, role, request id, 거부 사유를 남긴다. typed confirmation이 있어도 role gate를 우회하지 못한다. |
| 파괴적 작업 | active match set이 참조 중인 group/file hard-delete 요청 | application guard와 FK `RESTRICT`가 삭제를 막는다. 사용자는 먼저 match set retire 또는 다른 group으로 교체해야 한다. |
| 파괴적 작업 | forced promotion 실행 | `forced_promotion=true`는 consistency ERROR 승격 차단만 우회한다. source archive integrity gate, `source_file_group.state!='available'`, selected match set `integrity_alert=true`는 우회할 수 없다. actor, role, typed confirmation, ERROR case 목록, 사유를 report와 snapshot metadata에 남긴다. |
| Rollback | active release rollback 중 match set도 바뀜 | rollback 대상 snapshot이 `source_match_set_id`를 가지면 같은 transaction에서 현재 active match set을 `retired`로 내리고 대상 match set을 `active`로 복원한다. 대상의 `integrity_alert`는 rollback 직전 source quick reconcile 결과로 보존/재계산한다. legacy snapshot은 `알수없음/추정` 배지만 허용하고 정본으로 승격하지 않는다. |

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
- 성공 후 `source_file_group_id`, file count, group hash, size 합계, RustFS URI 요약

실수 방지:

- `roadname_hangul_full` 카드에 `위치정보요약DB` ZIP을 올리면 파일명/source 구조 검증에서 실패한다.
- generic "아무 파일이나 올리기"는 기본 UI에서 제거한다.
- 같은 브라우저 drag-and-drop으로 여러 category 파일을 한번에 뿌리는 기능은 1차 구현에서 금지한다. 사용자가 category별로 명시적으로 올리는 것이 목적이다.

### 기준년월 UX

규칙:

- `user_yyyymm` 입력은 upload session 생성 전에 필수다.
- 파일명이나 내부 member에서 `YYYYMM`/`YYMM`을 추론할 수 있으면 input 기본값으로 채운다.
- 추론할 수 없으면 현재 날짜 기준 `YYYYMM`을 input 기본값으로 채운다. 예를 들어 2026-06-14에는 `202606`을 제안한다.
- UI 기본값은 제안안일 뿐이며, 백엔드는 사용자가 제출한 `user_yyyymm`이 없으면 세션을 만들지 않는다.
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
| category별 파일 group | label, `user_yyyymm`, group_kind, file count, 대표 filename, group hash 앞 12자, state |
| optional 검증 자료 | 포함/생략, 마지막 validation 결과 |

현재 구성 조회 순서는 `ops.serving_releases.dataset_snapshot_id` → `ops.dataset_snapshots.source_match_set_id` → `ops.source_match_sets`다. 이 FK 경로에서 match set 연결을 찾을 수 없으면 다음처럼 표시한다.

```text
현재 DB를 만든 원천 매칭 정보: 알수없음
사유: 이 DB는 T-109 source match set 도입 전에 생성되었거나, 백업 복원 과정에서 match set metadata가 없습니다.
```

이 경우에도 기존 `load_manifest`, `load_jobs.payload.source_set`, `load_consistency_reports.source_set`, `ops.dataset_snapshots.source_set` JSONB에서 추정 가능한 정보는 "추정" 배지로 표시한다. 추정값은 match set 정본으로 저장하지 않는다.

## 검증 케이스 확장

현재 C1~C10은 유지한다. optional 자료를 활용하는 새 검증은 C11부터 추가한다. 구현 전에 `ops.consistency_case_samples.case_code` CHECK를 C11 이상도 허용하도록 완화해야 한다. 기존 CHECK가 C1~C10만 허용하는 상태에서 sample insert를 추가하면 validation job이 실패한다.

필수 migration:

```sql
ALTER TABLE ops.consistency_case_samples
  DROP CONSTRAINT IF EXISTS ops_consistency_case_samples_case_code_check;

ALTER TABLE ops.consistency_case_samples
  ADD CONSTRAINT ops_consistency_case_samples_case_code_check
  CHECK (case_code ~ '^C\d+$');
```

실제 constraint 이름은 Alembic migration에서 현재 DB introspection 또는 기존 migration 정의를 확인해 맞춘다.

제안:

| 코드 | 이름 | 입력 자료 | 생략 조건 |
|------|------|-----------|-----------|
| C11 | 출입구 원천 간 거리 검증 | `roadaddr_entrance_full`, `roadaddr_building_shape_bundle`, 전자지도 `TL_SPBD_ENTRC`, `locsum_full` | 건물 도형 bundle이 없으면 bundle 비교 skip |
| C12 | 건물 도형 bundle connection line 검증 | `roadaddr_building_shape_bundle`, 전자지도 도로 layer | bundle 없으면 skip |
| C13 | 상세주소 동 containment 검증 | `detail_dong_shape_bundle`, `detail_address_db_full`, 전자지도 `TL_SPBD_BULD` | 둘 중 하나 없으면 skip |
| C14 | 국가지점번호 grid/center 검증 | `national_point_grid_shape`, `national_point_grid_center`, `tl_sppn_makarea` | 둘 다 없으면 skip |
| C15 | 민원행정기관 POI 주소 거리 검증 | `civil_service_institution_map`, geocoder 결과 | 민원행정기관전자지도 없으면 skip |
| C16 | 주소DB/건물DB row/key drift 검증 | `address_db_full`, `building_db_full` | 해당 자료 없으면 skip |
| C17 | 내비 지번 member coverage 검증 | `navi_full` 내부 `match_jibun_*.txt`, `tl_juso_parcel_link` | `navi_full.metadata.match_jibun_present=false`이면 skip |

각 consistency report에는 다음을 추가한다.

```json
{
  "validation_inputs": {
    "national_point_grid_center": {
      "state": "skipped",
      "reason": "match set item omitted",
      "source_file_group_id": null
    },
    "roadaddr_building_shape_bundle": {
      "state": "used",
      "source_file_group_id": "...",
      "group_sha256": "...",
      "user_yyyymm": "202604",
      "files": [
        { "source_file_id": "...", "part_kind": "sido", "part_key": "11", "sha256": "..." }
      ]
    }
  }
}
```

UI는 C1~C10을 특별 취급하지 않고 API가 내려주는 case definition 순서대로 탭을 그린다. 새 C11+가 들어와도 가로 스크롤 탭과 sample table이 깨지지 않아야 한다. 1차 구현부터 `ops.consistency_case_definitions`를 정본으로 사용하므로 UI는 DB registry 기반 case catalog API만 의존한다. `CASE_DEFINITIONS` 정적 tuple은 seed/fallback 근거일 뿐 UI 계약이 아니다.

## 보강 자료 활용 원칙

### 도로명주소 건물 도형

직접 활용 가능성은 있지만 1차 구현에서는 검증용으로만 넣는다.

권장 단계:

1. `roadaddr_building_shape_bundle` 파일 registry/validation 구현
2. 기존 `src/kortravelgeo/loaders/building_shape_bundle.py`와 `scripts/compare_building_shape_bundle.py`의 layer/key 비교 로직을 registry/match set 입력과 연결
3. staging table 또는 streaming validator로 `TL_SPBD_ENTRC`와 기존 출입구 원천 비교
4. C11/C12 report 생성
5. 거리/coverage가 개선되는 케이스가 충분히 확인되면 별도 ADR로 대표 좌표 scoring 변경

금지:

- `TL_SGCO_RNADR_MST`를 `tl_spbd_buld_polygon`에 덮어쓰기
- `TL_SPBD_ENTRC`를 source priority 정의 없이 `mv_geocode_target`에 바로 union

### 건물군 내 상세주소 동 도형

일반 도로명주소 좌표 개선이 아니라 상세주소 기능과 검증용이다.

권장 단계:

1. `detail_dong_shape_bundle` 업로드/검증
2. 기존 `src/kortravelgeo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`의 상세주소 동/전자지도 overlap 비교 로직을 registry/match set 입력과 연결
3. `detail_address_db_full`과 match set optional pair 구성
4. C13 containment/key overlap 검증
5. 후속 상세주소 geocode feature에서 별도 endpoint 또는 `match_kind='detail'`로 사용

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
        "source_file_group_id": "...",
        "group_kind": "single_file",
        "group_sha256": "...",
        "files": [
          {
            "source_file_id": "...",
            "filename": "202605_도로명주소 한글_전체분.zip",
            "sha256": "...",
            "size_bytes": 123,
            "storage_uri": "rustfs://..."
          }
        ],
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
2. 없으면 manifest 기반 read-only reconstructed match set을 `restored_from_backup` 상태로 생성할지 사용자에게 묻기. 이 reconstructed match set은 원천 archive 존재와 hash를 확인하기 전까지 rebuild 입력으로 바로 활성화할 수 없다.
3. 각 `source_file_group_id`의 child `source_file_id`와 RustFS object 존재 여부를 확인하고, object가 있으면 size/SHA-256을 manifest metadata와 대조한다.
4. object가 없거나 child file coverage가 깨지면 UI에 `db_missing_object`, `source_file_unavailable`, `source_file_group_incomplete` 표시
5. active release의 current source 구성을 표시. 정보가 부족하면 `알수없음`

restore entrypoint별 source 검증:

| 진입점 | source 검증 |
|--------|-------------|
| 새 빈 DB에 `pg_restore` | restore finalize 직후 manifest source block을 읽고 위 검증 순서를 실행한다. |
| ADR-036 rename hot-swap | rename/smoke가 끝난 직후 source quick reconcile을 1회 실행한다. active snapshot의 `source_match_set_id`가 있으면 RustFS object availability를 확인하고, 없으면 legacy `source_set` 추정 표시만 허용한다. |
| restore 후 나중에 원천 archive 재연결 | 재연결 action은 object head/SHA-256을 manifest 값과 대조한 뒤 stub group/file을 `validating`으로 전환하고 구조 validator를 다시 실행한다. |

`restored_from_backup` 생성 절차:

1. 사용자 승인 후 한 transaction에서 manifest의 `source_match_set` block을 읽는다.
2. category item마다 `ops.source_file_groups` stub을 만든다. 기본 `state='missing'`, `validation_state='unknown'`, `group_sha256=manifest.group_sha256`, `user_yyyymm=manifest.yyyymm_by_category[category]`다. 이 `group_sha256`은 manifest 원본값일 뿐 아직 현재 RustFS object로 재검증된 값이 아니므로, `metadata.manifest_group_sha256`에도 보존하고 `available` 전 재계산 대상임을 표시한다.
3. manifest의 file entry마다 `ops.source_files` stub을 만든다. object가 아직 확인되지 않았으면 `state='missing'`, `validation_state='unknown'`, `storage_uri=manifest.storage_uri`, `sha256`/`size_bytes`는 manifest 값을 저장한다.
4. `ops.source_match_set_items`는 위 stub group을 참조한다. `omitted_optional`은 기존 `omitted=true` item으로 복원한다.
5. `ops.source_match_sets.state='restored_from_backup'`로 저장한다. legacy manifest에 canonical `source_set_hash`가 없으면 NULL을 허용한다.
6. restore 직후에는 rebuild 버튼을 비활성화한다.
7. object availability scan 또는 수동 재연결로 object가 확인되면 group/file을 `missing -> validating`으로 전환하고, RustFS object를 streaming rehash해 child `sha256`/`size_bytes`와 group `group_sha256`을 재계산한다. 재계산값이 manifest 값과 다르면 `quarantined` 또는 reconciliation issue로 보내고, match set은 `restored_from_backup`에 남긴다.
8. hash/size 재계산과 구조 validator가 모두 통과해 validator가 `passed` 또는 `warning`을 기록한 뒤에만 group/file을 `available`로 바꾼다. `validation_state='unknown'`인 stub은 `available`이 될 수 없다.
9. 모든 필수 group이 `available`이면 **먼저 canonical `source_set_hash`를 산출**(legacy manifest로 NULL이던 경우 새로 계산)한 뒤 match set을 `restored_from_backup -> revalidatable -> validate -> validated` 순서로 복구한다(revalidatable 진입 시 hash가 채워져 있어 `source_set_hash` CHECK를 만족 = M-A 옵션 2). 직접 active 승격은 금지하고, `activate` atomic swap을 별도로 요구한다.

## 구현 순서 제안

### 1단계: 문서/스키마/DTO

- category catalog 상수 추가
- `SourceFileCategory`, `SourceFileGroup`, `SourceFile`, `SourceMatchSet` DTO 추가
- Alembic migration으로 `ops.source_*` 테이블 추가
- Alembic만 갱신하지 않는다. fresh `ktgctl init-db`의 정본 DDL인 `src/kortravelgeo/infra/sql.py` `SCHEMA_SQL`/`INDEX_SQL`과 사본 DDL `sql/ddl/001_schema.sql`을 같은 PR에서 함께 갱신한다.
- `ops.source_file_groups`, `ops.source_upload_sessions`, `ops.source_match_set_items.source_file_group_id`, `ops.dataset_snapshots.source_match_set_id`, `ops.consistency_case_definitions`, `ops.consistency_case_inputs`, `ops.consistency_case_samples.case_code` CHECK 완화 포함
- 기존 `ops` ID full-prefix rename migration과 admin API/DTO/OpenAPI 변경 포함
- 기존 `UploadSetStatus`는 유지
- `docs/architecture/data-model.md`와 `docs/architecture/address-db-schema.md` 갱신

### 2단계: 백엔드 registry와 upload session

- category별 upload session API
- 진행 중 upload session 목록/재개 API와 UI "재개 가능한 업로드"
- 같은 `category + user_yyyymm` 진행 중 session 409 응답과 기존 session 재개 안내
- `expires_at`/`registration_deadline_at` 기본값, janitor, `registration_expired` 전이
- `single_file`/`multi_part` group_kind별 upload slot 처리
- register 전 완료 slot 명시 교체(`replace`)와 검증 결과 무효화
- proxy header 기반 `RequestContext`, `require_role(min_role)` admin role gate, typed confirmation helper
- temp archive 저장
- archive hash/size 계산
- ZIP/7z/SHP 구조 validator
- RustFS `head_object`, `delete_object`, `put_file(metadata=...)`, multipart upload, `rehash_object`와 put/head/hash verify
- DB group/file registry insert
- file list/download/soft delete/restore

### 3단계: RustFS reconciliation

- prefix scan
- DB row scan
- issue 생성
- `pending_registration`, `registration_expired`, `source_file_unavailable`, `source_file_group_incomplete`, `delete_failed` issue type
- resolve action
- resolve 직전 DB/RustFS read-after-write 재확인
- duplicate object resolve의 active 정본 삭제 guard
- audit event
- UI 목록

### 4단계: Match set builder

- match set CRUD
- profile required/recommended/optional validation
- omission flag
- activate atomic swap, `invalid`·`restored_from_backup` -> `revalidatable` -> `validated` 복구 전이(`restored_from_backup`은 `revalidatable` 진입 전 canonical `source_set_hash` 선산출; active 승격은 별도 `activate` atomic swap이며 `revalidatable`에서 직접 불가)
- active/current display
- active match set 무결성 결손을 `integrity_alert`(state='active' 유지)로 표시(serving 장애 아님), 비-active `validated`는 `invalid`로 전환(`draft`/`restored_from_backup` pre-hash는 유지)
- `recompute_group_aggregates()`의 양방향 전파: 결손 시 (비-active validated)`invalid` / (active)`integrity_alert`(`draft`·`restored_from_backup` pre-hash 유지), 복구 시 (`invalid`·`restored_from_backup`)→`revalidatable`(`restored_from_backup`은 선-hash 산출) / active `integrity_alert` 해제 후보
- 기존 full load batch payload 조립 bridge
- rebuild 전역 advisory lock, stale running job 마감, consistency ERROR 승격 gate
- rollback atomic source match set swap과 forced promotion의 consistency ERROR 한정 audit 범위(source integrity/`integrity_alert` 우회 금지)

### 5단계: validation 확장

- C11+ case definition 추가
- DB case registry seed와 `GET /v1/admin/consistency/case-definitions` API 추가
- `ops.consistency_case_samples.case_code` CHECK 완화 migration 검증
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
| upload session creation requires user_yyyymm | 기준년월 없이는 저장 불가 |
| source file group stores group_sha256 and child file metadata after register | DB metadata 정본 |
| multi_part sido group requires 17 part slots before register | SHP 3종 multi-file 모델 고정 |
| electronic map requires 11 master layers but loads 9 serving layers | M1 결정 고정 |
| TL_SPRD_INTRVL uses DBF-only validation profile | L2 회귀 방지 |
| multipart upload resumes and aborts cleanly | multipart/resumable 업로드 결정 고정 |
| multipart resume detects missing storage upload id | DB part 기록과 RustFS multipart 상태 불일치 복구 |
| upload sessions list returns resumable in-progress sessions | 브라우저 종료 후 재개 진입점 |
| duplicate category yyyymm upload session returns 409 with resumable session | 중복 세션/중복 object 방지 |
| completed slot replacement invalidates previous validation | register 전 slot 보정 경로 |
| upload session parts survive API restart | multipart 진행 상태 DB 영속화 |
| pending registration object is not classified as orphan before deadline | 비연속 업로드/등록 모델 |
| expired registration object becomes registration_expired not auto-deleted | deadline 이후 수동 처리 |
| upload janitor uses PostgreSQL advisory lock and only aborts unfinished multipart | janitor 실행 정책과 자동 삭제 경계 |
| register can be retried after DB insert failure | storage-first 복구 경로 |
| register reuses upload SHA and avoids duplicate archive reads | register 성능 회귀 방지 |
| recompute_group_aggregates updates group after child state change | group 파생값 단일 계산 지점 |
| recompute_group_aggregates promotes recovered invalid set to revalidatable | 복구 상향 전파 |
| admin role gate reads trusted RequestContext | proxy header 기반 권한 모델 고정 |
| admin role gate blocks destructive actions | 파괴적 액션 보호 |
| duplicate sha256 creates warning not hard error | 중복 탐지와 허용 분리 |
| soft delete blocks new match set group selection | 삭제 정책 |
| soft deleted group restore verifies RustFS object before available | 삭제 복구 경로 |
| hard delete blocks active match set group reference | active 데이터 보호 |
| reconciliation detects db_missing_object | RustFS 직접 삭제 |
| reconciliation detects object_missing_db | RustFS 직접 추가 |
| reconciliation quick skips unchanged etag/size and deep rehashes changed object | 손상 탐지와 운영 I/O 비용 통제 |
| reconciliation handles bucket-wide loss as integrity_alert/invalid propagation | RustFS bucket 전체 손실 복구 |
| reconciliation detects orphaned_multipart | 미완 multipart 용량 누수 방지 |
| match set requires build_required files | DB 구성 필수 자료 |
| match set references one group per category | M12/L9 모델 고정 |
| match set records omitted optional validation | 검증 자료 생략 플래그 |
| match set activate swaps existing active atomically | one-active unique 위반 방지 |
| active match set keeps active+integrity_alert on object loss and clears it after recovery | one-active 슬롯/serving 유지, state-결손 분리 |
| active match set validate-in-place clears integrity_alert without changing state | active alert 해제 API 경로 |
| non-active match set goes invalid then revalidatable after object recovery | 비-active 원천 결손 복구 전이 |
| rollback swaps source match set atomically and recalculates integrity_alert | rollback one-active invariant |
| case definitions are loaded from DB registry | C11+ 동적 case catalog |
| fresh init-db schema matches Alembic head for ops source registry | `infra/sql.py`와 Alembic drift 방지 |
| fresh init-db allows C11 consistency sample insert | `case_code` CHECK 완화 회귀 방지 |
| rebuild bridge emits existing full_load_batch children | 기존 loader 재사용 |
| rebuild integrity mismatch blocks child enqueue | 사용 직전 RustFS 변조 방어 |
| rebuild stale running job is failed before restart | 적재 중 프로세스 죽음 복구 |
| rebuild consistency ERROR blocks promotion unless forced | ERROR gate와 강제 승격 audit |
| forced promotion cannot bypass source integrity gate | 원천 archive 무결성 우회 금지 |
| rebuild materialize failure leaves snapshot and release unchanged | 실패 적재가 운영 상태를 바꾸지 않음 |
| run-validation integrity mismatch records failed input not skipped | 검증 자료 손상과 생략 구분 |
| restored_from_backup creates missing stub groups and files | 복원 manifest FK/CHECK 충족 |
| restored_from_backup relink validates before available | `unknown` 상태의 available 방지 |
| restored_from_backup recomputes group_sha256 before available | manifest hash 신뢰 경계 |
| backup restore missing source objects surfaces unavailable state | DB 백업과 원천 archive 보존 경계 |
| restore hot-swap runs source quick reconcile | rename 복원 source 검증 |
| forced promotion records consistency ERROR gates it bypasses | 강제 승격 audit 완결성 |
| GeoIP gate still protects admin source APIs | GeoIP와 admin role gate 경계 |
| untrusted admin proxy headers are rejected | proxy header 기반 role gate 우회 방지 |

### 프론트엔드 단위 테스트

| 테스트 | 목적 |
|--------|------|
| category cards render fixed slots | generic upload 회귀 방지 |
| yyyymm inferred value requires user confirmation | 기준월 UX |
| upload progress percent renders | 업로드 percent 필수 |
| validation spinner/stage renders | 비-percent 단계 표시 |
| failed stage opens detail dialog | 실패 상세 로그 |
| match set omitted optional appears as skipped | optional 검증 생략 표시 |
| upload duplicate session dialog resumes or cancels existing session | 중복 세션 UX |
| soft deleted group restore action renders validation result | 복구 UI |
| current source config unknown fallback | `알수없음` 표시 |
| reconciliation issue actions render by issue_type | 정합성 복구 UI |
| C11+ tabs render dynamically | 새 검증 케이스 UI |

### 통합 테스트

처음에는 실제 전국 자료를 쓰지 않고 작은 fixture archive로 검증한다.

1. `roadname_hangul_full` fixture ZIP 업로드 → group/file registry 등록
2. `locsum_full` fixture ZIP 업로드 → group/file registry 등록
3. 축소된 `multi_part` fixture로 electronic map group 생성 → slot coverage 검증
4. RustFS fake client로 object metadata 확인
5. object 삭제 simulation → reconciliation `db_missing_object`
6. RustFS 미등록 object simulation → reconciliation `object_missing_db`
7. 미완 multipart simulation → reconciliation `orphaned_multipart`
8. DB에는 multipart part 기록이 있지만 RustFS multipart upload id가 없는 상태 → session `failed_storage_state`, slot 재업로드 필요
9. child missing 처리 → `recompute_group_aggregates` → 비-active `validated` 참조 match set `invalid`(`draft`/`restored_from_backup` pre-hash는 유지), active 참조 match set `integrity_alert=true`
10. match set 생성 → validation success
11. optional validation omitted → report skip flag
12. rebuild-db: registry hash와 일치하는 archive면 적재 진행 / RustFS object를 사용 후 다른 내용으로 교체한 뒤 rebuild → 적재 전 무결성 게이트가 mismatch를 잡아 적재 중단 + group `quarantined` + active는 `integrity_alert`, 비-active `validated`는 `invalid`
13. run-validation: optional validation object를 register 후 교체한 뒤 실행 → `validation_inputs`가 `failed/source_integrity_mismatch`로 남고 `skipped`로 오분류되지 않음
14. backup restore: manifest의 match set metadata는 복원됐지만 RustFS object가 없는 상태 → UI/API가 `restored_from_backup` read-only 상태와 `source_file_unavailable`을 함께 노출
15. 진행 중 upload session 10/17 part 완료 상태에서 API 재시작 → 목록 API로 세션을 찾아 나머지 part 업로드 후 register 성공
16. active match set의 참조 object 삭제 → `state='active'` 유지 + `integrity_alert=true`(슬롯·serving 유지) → 같은 hash object 재연결·active validate-in-place → `integrity_alert=false` 복구. (비-active는 invalid→revalidatable→validate→validated)
17. rollback 대상 snapshot이 match set FK를 가진 상태에서 release rollback → 현재 active retire, 대상 match set active 복원, source quick reconcile로 `integrity_alert` 재계산
18. rebuild loader child 도중 heartbeat가 끊긴 job simulation → 다음 rebuild가 stale job을 failed로 마감하고 staging을 재초기화
19. rebuild 후 consistency ERROR simulation → 기본 승격 차단 / typed confirmation 강제 승격 시 `forced_promotion=true` 기록. source integrity mismatch 또는 selected match set `integrity_alert=true`는 forced promotion으로 우회 불가
20. 같은 category/yyyymm upload session 생성 경쟁 → 두 번째 요청은 `409`와 기존 session resume payload 반환
21. register 전 완료 slot 교체 → 기존 validation/hash 무효화 후 새 file만 register
22. `soft_deleted` group restore → RustFS head/hash 검증 후 `validating -> available` 또는 `missing/quarantined`
23. registration deadline 경과 object → `registration_expired` issue로 표시되고 자동 삭제되지 않음
24. restore hot-swap 직후 quick reconcile → source object 결손이면 active serving 유지 + 재구성 불가 경고
25. `restored_from_backup` stub 재연결 → group/file은 `unknown` 상태로 available 불가(`missing` → `validating` → storage rehash/validator → `available`), 모든 필수 group이 `available`이면 canonical `source_set_hash` 선산출 후 match set `restored_from_backup` → `revalidatable` → `validate` → `validated`
26. RustFS bucket 전체 손실 simulation → 모든 registry object가 unavailable로 표시되고 active는 `integrity_alert`, 비-active `validated`는 `invalid`
27. epost fetch 실패/ZIP 구조 불일치/기준월 mismatch → 핵심 rebuild에는 영향 없이 fetch session failed 또는 warning report로 기록

실제 자료 선택형 테스트는 `KTG_SLOW_REAL_DATA=1`일 때만 실행한다.

## 운영 주의점

- RustFS object는 기본 무기한 보존이므로 저장소 용량 모니터링이 필요하다. category별 object 수, 총 size, 최근 30일 증가량, `quarantined`/`soft_deleted`/미등록 stored object size를 admin UI와 운영 metric에 노출한다.
- 자동 삭제는 1차 구현 범위의 기본 동작으로 두지 않는다. 다만 용량 임계치 초과 시 오래된 `soft_deleted`/`quarantined` object를 archive tier로 옮길지, typed confirmation 기반 bulk hard-delete를 허용할지, 별도 cleanup 배치를 둘지는 후속 ADR에서 결정한다.
- 미등록 stored object는 무기한 보존 대상이 아니다. reconciliation에서 발견되면 생성 시각, 예상 category, size를 표시하고 수동 import/delete 후보로 노출한다.
- object 삭제는 UI에서 typed confirmation을 요구한다.
- `ops.source_*` registry row는 감사·재구성 근거이므로 기본 운영에서 물리 DELETE하지 않는다. 삭제는 `state` 전환으로 표현하고, FK는 `RESTRICT`/application guard와 audit event로 보호한다.
- DB registry가 있어도 RustFS object가 없으면 DB 재구성은 불가능하다.
- 백업 archive만으로는 원천 파일 RustFS object가 복원되지 않는다. 백업 manifest는 source file metadata를 담고, RustFS 원천 archive 보존은 별도 저장소 정책이다.
- `source_file_group_id`와 `source_file_id`는 한 환경 안의 registry id다. 다른 환경으로 object를 옮기면 `group_sha256` 또는 `sha256 + size + category + user_yyyymm + part_kind + part_key`로 import matching해야 한다.
- `user_yyyymm`은 사용자가 확정한 값이므로 파일명 추론과 달라도 감사 로그에 남긴다. 이를 조용히 자동 수정하지 않는다.
- optional 검증 자료가 없어서 skip된 케이스는 성공이 아니라 `skipped`다. UI와 report에서 명확히 구분한다.

## 후속 결정과 ADR

T-109 구현 방향의 핵심 선택지는 ADR-049로 확정한다. 구현 PR은 ADR-049를 기준으로 schema/API/DTO/UI를 작성한다.

확정된 결정:

1. 원천 파일 registry는 `ops.source_file_groups`와 `ops.source_files` 별도 테이블로 두고 `ops.artifacts`와 분리한다.
2. `roadaddr_entrance_full`과 `zone_shape_full`은 `serving_recommended` 기본값으로 두되, `serving_minimal`에서는 생략 가능하게 한다.
3. optional 검증 자료 생략은 match set item의 `omitted=true`와 consistency report `validation_inputs.skipped`로 기록한다.
4. RustFS hash mismatch 탐지는 `quick`/`deep` reconciliation으로 처리한다. 변경 감지 object나 `deep` scan 대상은 object 전체를 streaming 재해시해 즉시 확정한다. DB hash 갱신은 재해시 결과와 사용자 typed confirmation이 있을 때만 허용한다.
5. incremental update upload는 T-109 범위에서 제외한다.

아직 별도 운영 ADR이 필요한 항목:

1. RustFS 용량 관리 정책: 기본 무기한 보존을 유지하되, archive tier, soft-deleted object retention, 미등록 stored object cleanup SLA를 확정한다.
2. 보강 자료가 실제 serving 좌표 ranking에 편입되는 조건: C11+ 검증 결과와 feature flag 기준을 별도 ADR로 확정한다.
