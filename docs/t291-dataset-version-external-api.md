# T-291: 데이터셋 버전 외부 공개 API + admin 버전 관측

## 상태

- 상태: 설계 확정(문서만) — 구현은 T-291a~e 후속
- 요청일: 2026-08-26
- 사용자 요구(원문 요지): "백업본, 서비스 중인 데이터셋의 고유번호(혹은 해시)를 저장하고
  그것과 추가 정보(데이터셋 날짜 등)를 외부에서 확인할 수 있는 API와 확인/관리용 admin UI
  요소 추가. 외부에서 주소 DB가 바뀌었는지, 그 히스토리가 어떻게 되는지 확인 후 연관 데이터를
  업데이트하기 위함."
- 결정 기록: [ADR-067](adr/067-external-dataset-version-api.md) (기반 불변식 D0·버전 토큰·
  공개 범위·인증·저장 전략·admin UI 범위·엣지 표)
- 관련 문서: [t049-ops-metadata-schema.md](t049-ops-metadata-schema.md)(ops 스키마 기반),
  [t050-ops-hardening.md](t050-ops-hardening.md), [t109-backup-source-upload-management.md](t109-backup-source-upload-management.md)
- 관련 코드: `src/kortravelgeo/infra/sql.py`(ops DDL), `src/kortravelgeo/infra/admin_repo.py`
  (release/snapshot 기록·사영), `src/kortravelgeo/api/routers/v2.py`(v2 규약·
  `_V2_VALIDATION_RESPONSES`), `src/kortravelgeo/api/public_api_key.py`,
  `src/kortravelgeo/api/admission.py`, `kor-travel-geo-ui/components/admin/OpsPanel.tsx`

### 요구의 "저장" 부분에 대한 결론

식별자 저장은 **이미 존재한다** — `ops.dataset_snapshots.source_set_hash`(sha256 64-hex),
`ops.serving_releases`(uuid·상태·계보·`mv_hash`·`activated_at`), 백업은
`ops.artifacts.artifact_id`+`sha256`+manifest `active_serving{serving_release_id,…}`.
이 작업의 빈 곳은 저장이 아니라 (1) **서빙 전환이 빠짐없이 기록되는 것**(ADR-067 D0 — 현재
위반 5류: refresh 3경로 + 직접 서빙 base table 단독 적재 + benchmark 스크립트, T-291a가
수정), (2) **외부 노출 계약 + 변경 감지 시맨틱**, (3) **admin 관측**이다. 1차 스키마 변경은
0건이다(ADR-067 D5).

## 1. 외부 API 계약

공통 사항:

- 라우터 `src/kortravelgeo/api/routers/dataset.py` 신설 → `app.py`에서 `/v2` prefix로 include.
- 인증: `_api_key: None = Depends(require_public_api_key)` (ADR-064 공개 키 그대로, 스코프
  신설 없음). GeoIP KR 게이트(ADR-037)는 전역 적용을 그대로 받는다(`geoip_open_paths` 미추가,
  403은 기존 legacy envelope `E0403` 유지).
- v2 공통 envelope `{status, query_id, input}` + `response_model_exclude_none=True`(ADR-060).
- 검증 오류는 구조화 400 `V2ErrorEnvelope`(ADR-061). 배선 2곳: `_V2_VALIDATION_RESPONSES`는
  `src/kortravelgeo/api/routers/v2.py`에 모듈 프라이빗으로 정의되어 있으므로 재export하거나
  공용 위치로 승격해 `routers/dataset.py`에서 사용하고, `app.py`의
  `_VALIDATION_STRUCTURED_400` 하드코딩 튜플에 신규 경로를 추가한다.
- 응답 헤더 `Cache-Control: no-store` — 변경 감지 엔드포인트가 중간 캐시에 얹히면 감지 지연이
  계약 위반처럼 보인다. v2 공통 규약 문서(`docs/api-reference/v2/README.md`)에 이 헤더 규약을
  신설 조항으로 추가한다(v2 첫 사례).
- admission: `/v2/dataset/*`는 전용 `dataset` scope + **전역 `address` 예산에서 제외**
  (ADR-067 D3). 현재 구조는 전역 `address` scope(모든 `/v1/address/*`·`/v2/*`) 위에
  엔드포인트 scope 6종이 추가로 얹히는 형태고 전부 기본 비활성이다. 주의 —
  `scopes_for_path`는 `_is_public_address_path`가 거짓이면 **빈 튜플로 조기 반환**하므로, 그
  판정에서 `/v2/dataset/*`를 빼면 전용 scope까지 함께 사라진다. 올바른 수정은 판정 분리다:
  "scope 대상인가"와 "전역 예산 대상인가"를 나눠, dataset 경로는 endpoint scope는 얻되 전역
  `address` scope 획득만 건너뛴다. 구현 지점: `admission.py`의 `_SCOPE_SETTING_NAMES`·
  `_endpoint_scope_for_path`·`scopes_for_path`(전역 예산 제외 분기) + `Settings` 1개 +
  `build_admission_controller` 분기 1개.
- geo_cache는 `geocode`/`reverse` 호출 내부의 opt-in 캐시라 신규 라우트에 적용되지 않는다
  (확인 완료) — 별도 제외 작업 불필요.
- 권장 폴링 주기 ≥ 60초를 api-reference에 명문화한다.

### 1.1 `POST /v2/dataset/version` — 현재 버전 + 변경 감지 (폴링 대상)

요청(모든 필드 선택):

```json
{ "known_version": "dv1-4c2e0b7a9d315f68c0aa41e2b8d97f13" }
```

응답(변경된 경우):

```json
{
  "status": "OK",
  "query_id": "…",
  "input": { "known_version": "dv1-4c2e0b7a9d315f68c0aa41e2b8d97f13" },
  "available": true,
  "changed": true,
  "known_version_found": false,
  "current": {
    "version_token": "dv1-9f31c8ab02de47f6a1b5c033e8d21c70",
    "activated_at": "2026-08-20T03:12:45+09:00",
    "change_type": "full",
    "reference_months": {
      "juso": "202607", "parcel_link": "202607", "locsum": "202606",
      "navi": "202606", "shp": "202606"
    },
    "reference_months_mixed": true
  }
}
```

- `change_type`은 **2종** — `"full"`(전체 재동기화 필요) / `"delta"`(증분 갱신 가능).
  내부 `release_kind` 매핑: `full_load|restore|manual_rebuild|rollback → "full"`,
  `daily_delta → "delta"`. `"revert"`는 두지 않는다(ADR-067 D2 기각 사유 — hot-swap rollback
  사건의 1:1 노출).
- `known_version` 미제공 시 `changed`/`known_version_found` 생략.
- active release 0건이면 `{"status":"OK", …, "available": false}`(`current` 생략, HTTP 200 —
  소비자 오류 분기 방지).
- `known_version_found: false` = 그 토큰이 현재 원장에 없음(복원 등으로 이력 리셋) →
  **전체 재동기화** 규약.
- `reference_months` 도출 실패 시 필드 생략 — 그 경우 토큰만이 신뢰 신호.
- `known_version` 형식 검증: `^dv1-[0-9a-f]{32}$` 불일치 → 구조화 400(`error.field` 지정).

### 1.2 `POST /v2/dataset/history` — 변경 이력

요청:

```json
{ "since_version": "dv1-4c2e…", "limit": 20, "cursor": null }
```

- `since_version`(선택): 이 토큰의 활성화 시각 이후 항목만(자신 제외). `limit` 1~100 기본 20.
  `cursor` = opaque keyset 커서(계약상 파싱 금지).

응답:

```json
{
  "status": "OK", "query_id": "…",
  "input": { "limit": 20 },
  "since_found": true,
  "entries": [
    { "version_token": "dv1-9f31…", "activated_at": "2026-08-20T03:12:45+09:00",
      "change_type": "full",
      "reference_months": { "juso": "202607" }, "reference_months_mixed": false },
    { "version_token": "dv1-77aa…", "activated_at": "2026-07-19T02:41:03+09:00",
      "change_type": "delta" }
  ],
  "next_cursor": "eyJ…"
}
```

- 정렬: `ordered_at`(= `COALESCE(activated_at, created_at)`) 내림차순, 동률 시 `version_token`
  내림차순 — tiebreak를 **토큰**으로 두는 이유는 커서가 내부 UUID를 담지 않기 때문이다(아래).
  `now()` µs 해상도라 동률은 실질적으로 발생하지 않으며, 순서는 표시용일 뿐 변경 신호는
  토큰뿐이다.
- 커서 payload = `{before_at, before_token}`(base64url, 내부 UUID 미포함). 사영 계층이 각 행의
  토큰을 계산한 뒤 `(ordered_at, version_token)` 사전순 조건으로 다음 페이지를 끊는다.
- 마지막 페이지면 `next_cursor` 생략. entry 모델은 §1.1의 `current`와 동일 모델
  (`DatasetVersionEntry` 1개).
- 포함 상태: `active`/`superseded`만 실전에 존재한다(`rolled_back`은 enum에만 있고 쓰는 코드가
  없음 — 사영 필터는 방어적으로 포함하되 계약은 의존하지 않음). `pending`/`failed`는 절대
  출현하지 않는다. `state` 필드 자체는 비노출.
- `since_found: false` = 이력 리셋 → 최신 페이지를 반환하고 전체 재동기화 규약.
- 이력 보존은 **비보증**(복원 시 백업 이후 이력 소멸 가능)을 명문화한다.
- 오류: `limit` 범위 밖·`cursor` 해석 실패·토큰 형식 불일치 → 구조화 400. cursor 오류의
  hint는 "이력 처음부터 재조회".

### 1.3 소비자 프로토콜 (api-reference 문서에 명문화, T-291c)

1. `known_version`을 포함해 폴링(≥60초). `changed:false` → 무동작.
2. `changed:true, known_version_found:true` → history를 `since_version`으로 소급,
   `change_type`별 갱신(`delta`=증분, `full`=전체) 후 새 토큰 저장.
3. `changed:true, known_version_found:false` → 전체 재동기화 + 새 토큰 저장.
4. 계약 4항: (a) 토큰은 불투명·동등 비교만 (b) 토큰 동일 ⇒ 미변경(D0 성립 전제), 역은 비보증
   (c) `reference_months`는 생략 가능하며 비단조(복원 시 역행 가능) (d) 이력 보존 비보증.

엣지 케이스별 거동 표는 [ADR-067 "결과"](adr/067-external-dataset-version-api.md) 절이 정본이다.

## 2. 저장/파생 설계 — 스키마 변경 0건

신규 테이블·컬럼·뷰·시퀀스·인덱스·Alembic 전부 없음. 전부 파생으로 구성한다.

- **토큰 파생** (`src/kortravelgeo/core/dataset_version.py` 신규 모듈, 순수 함수):

  ```
  version_token = "dv1-" + sha256("ktg.dataset.version:" + serving_release_id)[:32]
  ```

  파생 입력의 정규형은 **소문자 하이픈 포함 36자 UUID 텍스트**로 고정한다 — 사영은
  `uuid.UUID` 객체를, 백업 manifest는 `::text` 문자열을 주므로 양쪽에서 같은 토큰이 나와야
  한다(단위 테스트로 고정).

- **공용 사영 쿼리**(repository, 외부/admin 공용 — admin 확장 필드 fidelity의 원천):

  ```sql
  SELECT sr.serving_release_id, sr.state, sr.release_kind,
         COALESCE(sr.activated_at, sr.created_at) AS ordered_at,
         sr.previous_serving_release_id, sr.mv_hash,
         ds.dataset_snapshot_id, ds.source_set, ds.source_set_hash,
         ds.parent_dataset_snapshot_id
  FROM ops.serving_releases sr
  JOIN ops.dataset_snapshots ds USING (dataset_snapshot_id)
  WHERE sr.state IN ('active','superseded','rolled_back')
  ORDER BY ordered_at DESC
  LIMIT :limit  -- keyset 커서 조건은 사영 계층에서 (ordered_at, version_token)으로 적용
  ```

  "현재" = 기존 `state='active'` 단건 조회 재사용 — active ≤ 1은
  `idx_ops_serving_releases_one_active` partial unique index(T-049)가 DB에서 강제한다.

  **원장 성장 모델**: 사영 대상(active/superseded)은 T-291a 이후 daily delta 기준 연 ~365행씩
  자란다. 별도로 일일 restore drill이 `pending` restore 행 + snapshot 행을 매일 라이브 원장에
  남기지만(연 ~365행) 사영의 state 필터가 배제한다. 수천 행 스캔 + sha256 계산도 ms
  미만이므로 인덱스 추가는 불필요하고, "수백 행" 같은 고정 상한을 설계 근거로 삼지 않는다.
  drill 오염 정리는 T-291e에서 판단.

- **기준월 정규화기** `normalize_reference_months(source_set)` — `source_set` JSONB의 실전
  형태 **4가지**를 흡수한다(각 형태의 writer를 단위 테스트로 고정):
  - **형태 A**(rebuild 경로, `source_rebuild_service`):
    `{category: {source_file_group_id, group_sha256, user_yyyymm, effective_yyyymm}}` →
    `{category: effective_yyyymm ?? user_yyyymm}` (`effective_yyyymm`은 nullable — loader
    자체가 `user_yyyymm` 폴백을 쓰므로 정규화기도 동일 폴백).
    저장 시 top-level에 **비카테고리 키**가 섞인다: `load_batch_id`(admin_repo가 주입),
    `rebuild_metadata`(`_snapshot_source_set`이 주입) — denylist로 건너뛴다.
  - **형태 B**(추론 경로, writer 2곳): `admin_repo._infer_current_source_set`(7종 +
    `source` 키)과 `backup.infer_source_set`(6종, `source` 없음 — restore 후보 스냅샷이 이를
    복사). 형상: `{yyyymm_by_kind: {...}, mixed_yyyymm, source?}` → `yyyymm_by_kind` 사용.
  - **형태 C**(hot_swap/rollback 기록 경로): `{"hot_swap": {...}}` /
    `{"hot_swap_rollback": {...}}` 같은 기준월 없는 메타 전용 payload(빈 dict 아님 — `if not
    source_set` 판정으로는 놓친다) → **계보 폴백**:
    `parent_dataset_snapshot_id`를 최대 5 hop 소급해 최초 정규화 가능한 `source_set` 채택.
    끝까지 실패하면 `reference_months` 생략.
  - **형태 D**(flat map, `batch_dag._source_set` + 운영자 임의 payload):
    `{category: "YYYYMM"}` 문자열 map — 값이 `^\d{6}$`이면 그대로 채택. `str()` 평탄화로
    repr 문자열이 된 열화값은 무시하고 계보 폴백으로 넘어간다(열화 자체의 수정은 T-291e).
  - **비카테고리 키 denylist**: `load_batch_id`, `rebuild_metadata`, `source`,
    `yyyymm_by_kind`, `mixed_yyyymm`, `hot_swap`, `hot_swap_rollback` — map을 순회할 때
    건너뛴다(형태 A/C/D 공용).
  - **외부 키 어휘 고정**: 공개 map의 키는 enum
    `juso`/`parcel_link`/`locsum`/`navi`/`shp`/`roadaddr_entrance`/`sppn_makarea`/`pobox`로
    고정한다(ADR-067 D2). 형태 B는 이미 kind명이므로 그대로, 형태 A의 source category 코드는
    매핑표로 변환한다 — 정본은 `source_rebuild_service._CATEGORY_TO_LOAD_KINDS`(rebuild 경로가
    실제로 이 6개 category만 통과시킨다):
    `roadname_hangul_full → juso`와 `parcel_link` **두 키 모두**(한글 전체분 archive가 지번
    link의 원본이기도 하다), `locsum_full → locsum`, `navi_full → navi`,
    `electronic_map_full → shp`(shp_polygons_load의 원본 — `roadaddr_building_shape_bundle`은
    rebuild 경로에 연결되지 않는 category라 매핑 대상이 아니다), `zone_shape_full →
    sppn_makarea`, `roadaddr_entrance_full → roadaddr_entrance`. **`pobox` 키는 현재 어떤
    writer도 방출하지 않는 예약 키**다(형태 A: `epost_pobox_full`이 rebuild에 비연결, 형태 B:
    pobox kind 없음) — T-291a가 pobox 적재를 기록하게 될 때 추론 writer에의 추가 여부를 함께
    확정한다. 미지 category는
    **생략**한다(억지 통과보다 누락이 낫다 — 토큰이 신뢰 신호). 매핑표의 정본은 구현 시
    `core/source_categories.py`와 대조해 확정하고, **writer 형태별 픽스처가 키 어휘 동일성을
    단언**한다(T-291b) — 같은 데이터가 rebuild 경로와 추론 경로에서 다른 키로 나오면 소비자의
    `reference_months.juso` 참조가 조용히 빈다.
  - `reference_months_mixed` = 정규화 결과 값들이 서로 다르면 true.

  **계보 1 hop 근거(정정)**: hot-swap 릴리스의 `parent_dataset_snapshot_id`는
  `_insert_dataset_snapshot_and_release`가 **교체된(복원된) DB 안의** 당시 active release의
  snapshot으로 설정한다 — 즉 백업 시점의 형태 A/B 스냅샷이 1 hop 부모다. (restore 후보 단계에서
  manifest source_set을 복사한 `pending` 스냅샷은 new_database 모드에서 **라이브 DB**에
  남았다가 스왑으로 폐기되므로 부모가 아니다.) 연속 hot-swap이 누적된 경우에만 다중 hop이
  필요하며, 5 hop이면 충분하다.

- **`known_version`/`since_version` 역조회**: 파생 해시라 역산 불가 → 사영 결과 행들에 토큰을
  계산해 매칭한다(위 성장 모델 기준 수천 행 스캔 ms 미만).

- **구현 자유도**: 현재 버전 블록의 in-process TTL 캐시(5~10초)는 허용하되 계약이 아니다.

- **백업 식별**(요구의 "백업본" 부분): 추가 저장 불필요 — `ops.artifacts.artifact_id` +
  `sha256` + manifest `active_serving.serving_release_id`가 이미 있고, 토큰은 manifest의
  release id에서 파생 계산 가능하다(정규형 고정 덕분). 외부에는 백업 정보를 일체 노출하지
  않으며(ADR-067 D2), admin의 "백업 시점 버전 토큰" 표시는 T-291e에서 기록 위생과 함께 붙인다.

## 3. Admin UI 설계 — 기존 releases 표면 확장 (신규 엔드포인트·패널 없음)

`GET /v1/admin/ops/releases`와 OpsPanel의 releases 표가 이미 존재하므로(필드도
`serving_release_id`/`dataset_snapshot_id`/`release_kind`/`state`/`mv_hash` 대부분 보유),
**그 표면을 확장한다** — "중복 UI 없음" 원칙의 자기 적용(ADR-067 D6).

1. **`ServingRelease` DTO에 additive 필드**: `version_token`, `change_type`,
   `reference_months`, `reference_months_mixed` — 공용 사영에서 계산. openapi 재생성 +
   `gen:types` 필요(admin 전용 스키마라 외부 계약 아님).
2. **OpsPanel releases 표에 컬럼 추가**: `version_token`(shortHash+복사), `change_type`,
   기준월 요약 + `혼합` badge.
3. **행 상세 다이얼로그**(ManifestViewer 템플릿): 내부 id 상관(serving_release/snapshot),
   원본 `source_set` JSON, 정규화 결과·계보 hop 표시, **"외부 응답 미리보기"** —
   trusted-proxy 경유 실제 `POST /api/proxy/v2/dataset/version` 호출 결과를 JsonBlock으로
   렌더 + curl 스니펫 복사
   (`curl -X POST https://<host>/v2/dataset/version -H "X-KTG-API-Key: <키>" -d '{"known_version":"…"}'`).
   **미리보기의 한계**: trusted-proxy는 `require_public_api_key`를 신뢰 클라이언트로
   우회하므로 검증 대상은 응답 본문의 공개 범위뿐이다 — 인증 동작 검증은 live e2e가 담당.
4. **CurrentConfigTab '현재 serving 구성'에 `version_token` 행 + AdminHome 활성 release
   StatusCard에 토큰 1줄** (additive).
5. **관리 동작은 읽기 전용.** 키 발급/회수는 기존 SettingsPanel 담당. 이력 개변·수기 정정·
   토큰 회전 없음(ADR-067 D6).

## 4. 테스트 계획

- **단위**(T-291b): 토큰 파생 고정값(+UUID 객체/텍스트 동일성), 정규화기 형태 A/B/C/D ×
  denylist × `effective→user` 폴백 × 계보 폴백 × 실패 시 생략 — **writer별 실제 형상 픽스처로
  고정**, keyset 커서 왕복.
- **기록 완결**(T-291a): CLI refresh swap·postload execute_safe·replace_current 각각이
  release를 기록하는지, 일변동분 유래 refresh가 `daily_delta`로 라벨링되는지 — 수정 전
  코드에서 실패함을 먼저 확인(AGENTS.md Goal-Driven Execution).
- **계약**(T-291c): `known_version` 왕복(`changed:false`) → release 전환 후(`changed:true`),
  이력 리셋 픽스처에서 `known_version_found:false`, `^dv1-` 형식 400, `pending`/`failed`
  미출현, 외부 DTO에 내부 필드 부재(공개 범위 회귀 차단), `Cache-Control: no-store`.
- **live e2e**(T-291d): 신규 `dataset-version-live.spec.ts` — 키 발급 → `/v2/dataset/version`
  직접 호출(인증 경로) → admin 미리보기와 토큰 일치 → `known_version` 왕복 `changed:false` →
  history `since` 왕복. 기존 `admin-api-readonly`/`admin-browser-readonly`/
  `admin-api-query-matrix`에 확장 필드·limit/cursor 케이스 추가.

## 5. 구현 task 분해 (이번 PR은 문서만; a→b→c→d 의존, e 독립)

- **T-291a — 서빙 전환 기록 완결 (선행 조건, ADR-067 D0)**: 위반 5류 전부 —
  (1) `ktgctl load all-sidos --refresh` swap 경로, (2) `run_postload_maintenance(execute_safe)`
  의 `refresh_mv`, (3) `db_restore replace_current`의 active `restore` release 기록,
  (4) **직접 서빙 base table 단독 적재**(pobox/sppn_makarea/shp_polygons/bulk) — 공용
  post-loader recorder 하나를 두고 **REST 경로는 load job/batch 성공 종료 훅에서, CLI 경로는
  각 `ktgctl load <kind>` 명령 성공 종료 시** 호출한다(per-source CLI 명령은 `load_jobs` 행
  없이 로더를 직접 부르므로 job 종료 훅만으로는 CLI 절반이 미기록으로 남는다),
  (5) `scripts/benchmark_mv_refresh.py`의 라이브 shadow-swap. delta 계열 kind 유래는
  `daily_delta`, 그 외 단독 적재는 기존 규칙으로 라벨링. 주의: `record_mv_refresh_release`는
  `release_kind` 인자가 없고 `load_batch_id` 유무로만 `full_load`/`manual_rebuild`를
  파생하므로 **시그니처 확장이 필요**하다(순수 재배선이 아니다). 기록 누락 회귀 테스트 포함.
- **T-291b — 토큰·정규화기·공용 사영 (backend 내부만, 스키마 0건)**:
  `core/dataset_version.py`(파생식 + 정규형 고정 + 정규화기 4형태/denylist/폴백) + repository
  공용 사영 + keyset 커서 + 단위 테스트. API 미노출.
- **T-291c — 외부 v2 엔드포인트**: `dto/v2.py` DTO + `routers/dataset.py` +
  `_V2_VALIDATION_RESPONSES` 재export·`_VALIDATION_STRUCTURED_400` 배선 +
  `Cache-Control: no-store` + `/v2/dataset/*` 전용 admission scope(+전역 `address` 예산 제외) +
  `scripts/export_openapi.py` 재생성(CI drift) + **api-reference 4건**: 신규
  `docs/api-reference/v2/dataset-version.md`(소비자 프로토콜·보증·엣지 표),
  `docs/api-reference/README.md`(구현 범위·문서 지도), `docs/api-reference/llm-summary.md`
  (엔드포인트 표), `docs/api-reference/v2/README.md`(Cache-Control 규약 신설),
  `docs/t145-backpressure-failfast.md`(`KTG_API_DATASET_MAX_CONCURRENCY` 행 추가 — 유일한
  `KTG_API_*_MAX_CONCURRENCY` 열거처) + UI
  `npm run gen:types`. 계약 테스트 포함.
- **T-291d — admin 확장**: `ServingRelease` additive 필드 + OpsPanel releases 표 컬럼 +
  상세/미리보기/curl + CurrentConfigTab·AdminHome 행 + e2e(§4).
- **T-291e — 기록 경로 위생 (독립 후속)**: 백업 생성 시 `insert_artifact`에
  snapshot/release FK 정식 기입(실패 시 NULL 강등 유지), BackupsPanel "백업 시점 토큰" 컬럼 +
  ManifestViewer 1줄, hot-swap release 기록 시 계보의 yyyymm 블록을 자기 `source_set`에
  복사(신규 행 자체 완결화), `batch_dag._source_set`의 `str()` 평탄화(repr 열화) 수정,
  restore drill의 원장 `pending` 행 누적(연 ~365행) 정리 방안 판단.

## 6. 하지 않는 것

[ADR-067 "하지 않는 것"](adr/067-external-dataset-version-api.md) 절이 정본이다. 요약:
단조 번호/원장·ETag/304·webhook·내부 해시/UUID 노출·백업 정보 외부 노출·MV 내용 해시·v1
표면·라이브러리 공개 메서드·키 스코프·이력 편집 UI·1차 스키마 변경·`change_type: "revert"`.
