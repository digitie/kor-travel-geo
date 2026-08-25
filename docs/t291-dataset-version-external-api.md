# T-291: 데이터셋 버전 외부 공개 API + admin 버전 관측

## 상태

- 상태: 설계 확정(문서만) — 구현은 T-291a~d 후속
- 요청일: 2026-08-26
- 사용자 요구(원문 요지): "백업본, 서비스 중인 데이터셋의 고유번호(혹은 해시)를 저장하고
  그것과 추가 정보(데이터셋 날짜 등)를 외부에서 확인할 수 있는 API와 확인/관리용 admin UI
  요소 추가. 외부에서 주소 DB가 바뀌었는지, 그 히스토리가 어떻게 되는지 확인 후 연관 데이터를
  업데이트하기 위함."
- 결정 기록: [ADR-067](adr/067-external-dataset-version-api.md) (버전 토큰·공개 범위·인증·
  저장 전략·admin UI 범위)
- 관련 문서: [t049-ops-metadata-schema.md](t049-ops-metadata-schema.md)(ops 스키마 기반),
  [t050-ops-hardening.md](t050-ops-hardening.md), [t109-backup-source-upload-management.md](t109-backup-source-upload-management.md)
- 관련 코드: `src/kortravelgeo/infra/sql.py`(ops DDL), `src/kortravelgeo/infra/admin_repo.py`
  (release/snapshot 사영), `src/kortravelgeo/api/routers/`(v2 라우터·`require_public_api_key`),
  `kor-travel-geo-ui/components/admin/OpsPanel.tsx`

### 요구의 "저장" 부분에 대한 결론

식별자 저장은 **이미 존재한다** — `ops.dataset_snapshots.source_set_hash`(sha256 64-hex),
`ops.serving_releases`(uuid·상태·계보·`mv_hash`·`activated_at`), 백업은
`ops.artifacts.artifact_id`+`sha256`+manifest `active_serving{serving_release_id,…}`.
이 작업의 빈 곳은 저장이 아니라 **외부 노출 계약 + 변경 감지 시맨틱 + admin 관측**이고,
따라서 1차 스키마 변경은 0건이다(ADR-067 D5). 기록 경로의 사소한 위생(백업 artifact FK 기입
등)만 T-291d로 분리한다.

## 1. 외부 API 계약

공통 사항:

- 라우터 `src/kortravelgeo/api/routers/dataset.py` 신설 → `app.py`에서 `/v2` prefix로 include.
- 인증: `_api_key: None = Depends(require_public_api_key)` (ADR-064 공개 키 그대로, 스코프
  신설 없음). GeoIP KR 게이트(ADR-037)는 전역 적용을 그대로 받는다(`geoip_open_paths` 미추가,
  403은 기존 legacy envelope `E0403` 유지).
- v2 공통 envelope `{status, query_id, input}` + `response_model_exclude_none=True`(ADR-060).
- 검증 오류는 구조화 400 `V2ErrorEnvelope`(ADR-061) — `_V2_VALIDATION_RESPONSES`(dto/v2)와
  `_VALIDATION_STRUCTURED_400`(app.py) 양쪽 등록 필요.
- 응답 헤더 `Cache-Control: no-store` — 변경 감지 엔드포인트가 중간 캐시에 얹히면 감지 지연이
  계약 위반처럼 보이게 된다.
- admission은 기존 `/v2/` 전역 semaphore를 그대로 받는다(전용 scope 없음).
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

- 정렬: 항상 최신→과거(첫 항목이 현재 서빙과 일치하는 것이 일반). 마지막 페이지면
  `next_cursor` 생략. entry 모델은 §1.1의 `current`와 동일 모델(`DatasetVersionEntry` 1개).
- 포함 상태: 내부적으로 `active`/`superseded`/`rolled_back`(한때 실제 서빙된 것)만.
  `pending`/`failed`는 절대 출현하지 않는다. `state` 필드 자체는 비노출.
- `since_found: false` = 이력 리셋 → 최신 페이지를 반환하고 전체 재동기화 규약.
- 이력 보존은 **비보증**(복원 시 백업 이후 이력 소멸 가능)을 명문화한다.
- 오류: `limit` 범위 밖·`cursor` 해석 실패·토큰 형식 불일치 → 구조화 400. cursor 오류의
  hint는 "이력 처음부터 재조회".

### 1.3 소비자 프로토콜 (api-reference 문서에 명문화, T-291b)

1. `known_version`을 포함해 폴링(≥60초). `changed:false` → 무동작.
2. `changed:true, known_version_found:true` → history를 `since_version`으로 소급,
   `change_type`별 갱신(`delta`=증분, `full`/`revert`=전체) 후 새 토큰 저장.
3. `changed:true, known_version_found:false` → 전체 재동기화 + 새 토큰 저장.
4. 계약 4항: (a) 토큰은 불투명·동등 비교만 (b) 토큰 동일 ⇒ 미변경, 역은 비보증
   (c) `reference_months`는 생략 가능하며 비단조(복원 시 역행 가능)
   (d) 이력 보존 비보증.

엣지 케이스별 거동 표는 [ADR-067 "결과"](adr/067-external-dataset-version-api.md) 절이 정본이다.

## 2. 저장/파생 설계 — 스키마 변경 0건

신규 테이블·컬럼·뷰·시퀀스·인덱스·Alembic 전부 없음. 전부 파생으로 구성한다.

- **토큰 파생** (`src/kortravelgeo/core/dataset_version.py` 신규 모듈, 순수 함수):

  ```
  version_token = "dv1-" + sha256("ktg.dataset.version:" + serving_release_id)[:32]
  ```

- **공용 사영 쿼리**(repository, 외부/admin 공용 — admin 미리보기 fidelity의 원천):

  ```sql
  SELECT sr.serving_release_id, sr.state, sr.release_kind,
         COALESCE(sr.activated_at, sr.created_at) AS ordered_at,
         sr.previous_serving_release_id, sr.mv_hash,
         ds.dataset_snapshot_id, ds.source_set, ds.source_set_hash,
         ds.parent_dataset_snapshot_id
  FROM ops.serving_releases sr
  JOIN ops.dataset_snapshots ds USING (dataset_snapshot_id)
  WHERE sr.state IN ('active','superseded','rolled_back')
  ORDER BY ordered_at DESC, sr.serving_release_id DESC
  LIMIT :limit  -- + keyset 커서 조건
  ```

  인덱스 추가 없음(원장은 수백 행 이하). "현재" = 기존 `state='active'` 단건 조회 재사용 —
  active ≤ 1은 `idx_ops_serving_releases_one_active` partial unique index(T-049)가 DB에서
  이미 강제하므로 정렬 tiebreak는 방어적 관성일 뿐이다.

- **기준월 정규화기** `normalize_reference_months(source_set)` — `source_set` JSONB의 3가지
  실전 형태를 흡수한다:
  - 형태 A(rebuild 경로): `{category: {…, effective_yyyymm}}` → `{category: yyyymm}`
  - 형태 B(추론/manifest 경로): `{yyyymm_by_kind: {...}, mixed_yyyymm}` → 그대로 사용
  - 형태 C(hot_swap/rollback/빈 값): 정규화 불가 → **계보 폴백**: `parent_dataset_snapshot_id`
    를 최대 5 hop 소급해 최초 정규화 가능한 `source_set`을 채택(restore 스냅샷은 백업 manifest
    의 source_set을 복사해 두므로 실전은 1 hop). 끝까지 실패하면 `reference_months` 생략.
  - `reference_months_mixed` = 정규화 결과 값들이 서로 다르면 true.

- **`known_version`/`since_version` 역조회**: 파생 해시라 역산 불가 → 사영 결과 행들(≤수백)에
  토큰을 계산해 매칭한다. 커서 payload는 `{before_at, before_token}`(내부 UUID 미포함,
  base64url).

- **구현 자유도**: 현재 버전 블록의 in-process TTL 캐시(5~10초)는 허용하되 계약이 아니다.

- **백업 식별**(요구의 "백업본" 부분): 추가 저장 불필요 — `ops.artifacts.artifact_id` +
  `sha256` + manifest `active_serving.serving_release_id`가 이미 있고, 토큰은 manifest의
  release id에서 파생 계산 가능하다. 외부에는 백업 정보를 일체 노출하지 않으며(ADR-067 D2),
  admin에서 "백업 시점의 버전 토큰"을 보여주는 것은 T-291d의 기록 위생과 함께 붙인다.

## 3. Admin UI 설계

**신규 admin API**: `GET /v1/admin/ops/dataset-versions?limit=20&cursor=…` — §2 공용 사영 +
admin 확장 DTO `AdminDatasetVersion`(외부 필드 전부 + `serving_release_id`,
`dataset_snapshot_id`, `release_kind` 원값, `state`, `source_set_hash`, `mv_hash`, 정규화
원본/결과). 외부 DTO와 **별도 모델**로 둔다 — 공개 범위 역류 사고를 모델 수준에서 차단.

**UI(신규 페이지 없음 — `/admin/ops` OpsPanel 확장)**:

1. **"데이터셋 버전" 패널 1개 추가** — `loadAll`의 Promise.allSettled에 endpoint 1줄 +
   columns. 컬럼: `version_token`(shortHash+복사), `change_type`(+`release_kind` 원값 병기),
   `state`, `activated_at`, 기준월 요약 + `혼합` badge, `source_set_hash`(shortHash + HelpTip
   "외부 API의 `version_token`과 다른 값" 안내).
2. **행 상세 다이얼로그**(ManifestViewer 템플릿): 내부 id 상관(serving_release/snapshot),
   원본 `source_set` JSON, 정규화 결과·계보 hop 표시, **"외부 응답 미리보기"** —
   trusted-proxy 경유 실제 `POST /api/proxy/v2/dataset/version` 호출 결과를 JsonBlock으로
   렌더(공개 범위 회귀를 운영자가 눈으로 잡는 보안 리뷰 표면), curl 스니펫 복사
   (`curl -X POST https://<host>/v2/dataset/version -H "X-KTG-API-Key: <키>" -d '{"known_version":"…"}'`).
3. **CurrentConfigTab '현재 serving 구성'에 `version_token` 행 + AdminHome 활성 release
   StatusCard에 토큰 1줄** (additive).
4. **관리 동작은 읽기 전용.** 키 발급/회수는 기존 SettingsPanel이 담당 — 중복 UI 없음.
   이력 개변·수기 정정·토큰 회전 없음(ADR-067 D6).

## 4. 테스트 계획

- **단위**(T-291a): 토큰 파생 고정값, 정규화기 형태 A/B/C × 계보 폴백 × 실패 시 생략,
  keyset 커서 왕복.
- **계약**(T-291b): `known_version` 왕복(`changed:false`) → release 전환 후
  (`changed:true`), 이력 리셋 픽스처에서 `known_version_found:false`, `^dv1-` 형식 400,
  `pending`/`failed` 미출현, 외부 DTO에 내부 필드 부재(공개 범위 회귀 차단).
- **live e2e**(T-291c): 신규 `dataset-version-live.spec.ts` — 키 발급 → `/v2/dataset/version`
  → admin 미리보기와 토큰 일치 → `known_version` 왕복 `changed:false` → history `since` 왕복.
  기존 `admin-api-readonly`/`admin-browser-readonly`/`admin-api-query-matrix`에 신규 GET·패널·
  limit/cursor 케이스 추가.
- 테스트는 구현 전 코드에서 실패함을 먼저 확인한다(AGENTS.md Goal-Driven Execution).

## 5. 구현 task 분해 (이번 PR은 문서만; a→b→c 의존, d 독립)

- **T-291a — 토큰·정규화기·공용 사영 (backend 내부만, 스키마 0건)**:
  `core/dataset_version.py`(파생식 + 정규화기 3형태 + 계보 ≤5 hop) + repository 공용 사영 +
  keyset 커서 + 단위 테스트. API 미노출.
- **T-291b — 외부 v2 엔드포인트**: `dto/v2.py` DTO + `routers/dataset.py` + 400 배선 2곳
  (`_V2_VALIDATION_RESPONSES`/`_VALIDATION_STRUCTURED_400`) + `Cache-Control: no-store` +
  `scripts/export_openapi.py` 재생성(CI drift) + `docs/api-reference/` v2 문서(소비자 프로토콜·
  보증·엣지 표) + UI `npm run gen:types`. 계약 테스트 포함.
- **T-291c — admin API + UI**: `GET /v1/admin/ops/dataset-versions` + OpsPanel 패널 +
  상세/미리보기/curl + CurrentConfigTab·AdminHome 행 + e2e 확장(§4).
- **T-291d — 기록 경로 위생 (독립 후속)**: 백업 생성 시 `insert_artifact`에
  snapshot/release FK 정식 기입(실패 시 NULL 강등 유지), BackupsPanel "백업 시점 토큰" 컬럼 +
  ManifestViewer 1줄, hot-swap release 기록 시 계보의 yyyymm 블록을 자기 `source_set`에
  복사(신규 행 자체 완결화), `batch_dag.py`의 `source_set` 평탄화(repr 문자열 열화) 수정.

## 6. 하지 않는 것

[ADR-067 "하지 않는 것"](adr/067-external-dataset-version-api.md) 절이 정본이다. 요약:
단조 번호/원장·ETag/304·webhook·내부 해시/UUID 노출·백업 정보 외부 노출·MV 내용 해시·v1
표면·라이브러리 공개 메서드·키 스코프·이력 편집 UI·1차 스키마 변경.
