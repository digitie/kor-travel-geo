# ADR-067: 데이터셋 버전 외부 공개는 serving release 파생 opaque 토큰 + 최소 공개 원칙으로 한다

- 상태: proposed
- 날짜: 2026-08-26
- 결정자: 사용자 요청, claude 설계
- 관련: ADR-004(raw SQL repository)·ADR-017(batch DAG/MV swap)·ADR-033(ops 스키마)·
  ADR-036(hot-swap restore)·ADR-037(GeoIP gate)·ADR-038(v1/v2 분리)·ADR-039(라이브러리 공개
  범위)·ADR-060(v2 규약)·ADR-061(구조화 400)·ADR-064(공개 API key)
- 설계 정본: [`docs/t291-dataset-version-external-api.md`](../t291-dataset-version-external-api.md)
  (T-291)

## 컨텍스트

외부 소비자가 이 시스템의 주소 DB를 참조해 자기 쪽 파생 데이터를 유지한다. 그들에게 필요한
것은 "서빙 중인 주소 데이터셋이 바뀌었는가"를 값싸게 감지하고, 바뀌었다면 어떤 종류의 변경이
언제 있었는지 이력을 확인한 뒤 자기 데이터를 갱신하는 루프다. 현재는 이를 확인할 외부 표면이
없다 — 서빙 데이터셋의 정체성(`ops.dataset_snapshots.source_set_hash`,
`ops.serving_releases.mv_hash`, 계보, 상태)과 백업 식별자(`ops.artifacts.artifact_id`,
`sha256`, manifest의 `active_serving`)는 전부 내부 ops 스키마에만 있다(ADR-033).

버전 신호 설계에는 이 시스템 고유의 제약이 있다. ADR-036 hot-swap restore는 데이터베이스를
백업 시점으로 **통째로 교체**하므로, DB 안에 사는 어떤 카운터·원장도 함께 과거로 돌아간다.
또한 원천별 기준월이 서로 다른 혼합 상태가 정상 운영 상태다(C10 WARN은 품질 신호이지 버그가
아니다).

## 근거

세 가지 축이 설계를 결정한다.

1. **거짓 음성 불허** — "바뀌었는데 안 바뀌었다고 답하는" 실패만은 회복 경로가 없다(소비자가
   영원히 재동기화하지 않는다). 거짓 양성(안 바뀌었는데 바뀌었다고 답함)은 불필요한 재동기화
   1회로 끝나므로 허용한다.
2. **복원 내성** — hot-swap이 DB 전체를 되돌리는 시스템에서, DB 안에 사는 단조 카운터는 값이
   재사용되어 1을 위반한다. 토큰은 재사용이 구조적으로 불가능한 재료(uuid4)에서 파생해야 한다.
3. **최소 노출** — 이 표면은 운영 메타데이터를 외부에 여는 문이다. 소비자의 행동(재동기화
   여부·방식 결정)에 필요한 최소만 노출한다.

## 결정

### D0 — 기반 불변식: 모든 서빙 전환은 `ops.serving_releases`에 새 행을 만들어야 한다 (현재 미성립 — T-291a가 선행 조건)

이 계약의 기반 불변식이다. **현재 코드는 이를 세 경로에서 위반한다**:

1. `ktgctl load all-sidos --refresh`(기본 `swap=True`) — 전국 적재 문서화 경로가 release를
   기록하지 않는다.
2. `run_postload_maintenance(mode="execute_safe")` — `refresh_mv`로 서빙 세대를 통째로
   갱신하면서 release를 기록하지 않는다.
3. `db_restore mode="replace_current"` — 라이브 DB를 덮어쓰면서 `pending` 행만 남기고 active
   release를 만들지 않는다.

또한 `release_kind='daily_delta'`는 enum에만 있고 쓰는 코드가 없다 — 일변동분 적재 후 MV
refresh는 `manual_rebuild`로 기록된다.

이 상태로 외부 API를 열면 전국 데이터를 통째로 갈아끼워도 토큰이 유지되는 **거짓 음성**이
생긴다(근거 1 위반). 따라서 **T-291a(서빙 전환 기록 완결)가 외부 공개(T-291c)의 선행
조건**이다: 위 세 경로가 release를 기록하게 하고, 일변동분 유래 refresh를 `daily_delta`로
라벨링한다. 본 ADR의 나머지는 T-291a 이후의 세계를 서술한다.

### D1 — 버전 토큰은 active serving release에서 파생한 opaque 토큰으로 한다. 신규 저장 없음

```
version_token = "dv1-" + sha256("ktg.dataset.version:" + serving_release_id)[:32]   # hex 32자
```

`serving_release_id`는 uuid4이고, 파생 입력은 **소문자 하이픈 포함 36자 정규 텍스트 표기**로
고정한다(UUID 객체/manifest 문자열 어느 쪽에서 계산해도 동일해야 한다). 파생 토큰은 이력
리셋·복원 후에도 재사용되지 않는다.

계약의 전부는 다음 한 문장이다: **토큰이 같으면 서빙 데이터셋이 바뀌지 않았다(D0 성립 전제).
역은 보증하지 않는다**(동일 데이터 재적재도 새 토큰 = 허용된 과잉 감지). 토큰은 불투명
값으로, 동등 비교만 허용하고 파싱·정렬은 계약 위반이다.

기각한 대안:

- **epoch + 단조 seq 신규 원장 테이블** — hot-swap restore가 원장 테이블 자체를 백업 시점으로
  되돌린다. 백업 시점 seq=40, 라이브 seq=43 상태에서 복원하면 다음 발급이 41이 되어 같은 epoch
  안에서 토큰이 재사용된다. epoch 값이 스왑되는 DB 안에 있는 한 구조적으로 방어할 수 없고,
  "토큰 영구 비재사용" 보증이 거짓 약속이 된다. 테이블 2개·트리거·백필 비용은 덤이다.
- **`serving_release_id` 원값 노출** — 동작은 같지만 내부 핸들이 외부 계약에 결합된다. 파생
  1줄로 차단할 수 있는 결합이다.
- **`source_set_hash` / `mv_hash` 재사용** — 전자는 스냅샷 생성 경로(batch/추론/manifest 복사)
  별로 형상이 달라 같은 데이터에 다른 해시, 다른 데이터에 같은 해시가 모두 가능하다. 후자는
  `md5(viewdef || rowcount)` 수준이라 데이터 변경의 ground truth가 아니다.

### D2 — 외부 공개 필드는 4개 + 파생 플래그 1개뿐이다

`version_token`, `activated_at`, `change_type`, `reference_months`(원천별 YYYYMM map) +
파생 플래그 `reference_months_mixed`.

- `change_type`은 **2종**: `full_load|restore|manual_rebuild|rollback → "full"`,
  `daily_delta → "delta"`. 소비자의 행동 공간은 "전체 재동기화 / 증분 갱신" 둘뿐이므로
  `release_kind` 5종 원값을 노출하지 않는다.
  - 초안의 `rollback → "revert"` 3종안은 **기각** — `rollback` release의 유일한 생산자가
    hot-swap rollback이라 `revert` 노출은 "복원 후 롤백" 사고 타임라인을 1:1로 공개하는
    것이었다. 은닉을 위해 coarse하게 만든다는 자기 논리와 모순이므로 `full`로 흡수한다.
    소비자 행동은 어차피 전체 재동기화로 동일하다. (필요해지면 additive로 재도입 가능 —
    ADR-060.)
- 기준월은 원천별 map으로 공개한다 — 혼합 기준월이 정상 상태이므로 대표값 하나로 뭉개지
  않는다. 도출 불가 시 필드를 생략하고(exclude_none), 그 경우 토큰만이 신뢰 신호라는 규약을
  문서화한다.
- 내부 UUID·`source_set_hash`·`mv_hash`·`row_counts`·git/alembic/PostgreSQL 버전·`source_set`
  원본, 그리고 **백업 관련 정보 일체**(존재·시각·artifact id·sha256)는 비공개다.

### D3 — 인증·게이트는 기존 것을 재사용하고, admission scope만 분리한다

`require_public_api_key`(ADR-064) 그대로, 키 스코프 신설 없음. GeoIP KR 게이트(ADR-037)는
전역 적용을 그대로 받는다(`geoip_open_paths` 미추가). 버전 메타데이터는 같은 키로 접근 가능한
주소 데이터 본체보다 민감하지 않다.

admission은 현재 단일 `address` scope 하나뿐이고 기본은 **비활성**(`api_max_concurrency`
기본 None)이다. 폴링 전용으로 설계된 엔드포인트가 활성화 시 지오코딩 본체와 같은 예산을
소모하면 메타데이터가 본품을 굶길 수 있으므로, `/v2/dataset/*`에는 **전용 admission scope**를
둔다(T-291c, `_endpoint_scope_for_path` 1항목 + 설정 1개). admission 비활성 상태의
backpressure는 서버 측 TTL 캐시 + 권장 폴링 주기(≥60초) + 키 회수다.

### D4 — API 형태는 v2 POST 고정 + body 조건부 폴링으로 한다

`POST /v2/dataset/version`(요청 body `known_version` → 응답 `changed`/`known_version_found`)과
`POST /v2/dataset/history`(`since_version`/`limit`/opaque `cursor`). GET+ETag/304 조건부 요청은
기각 — 이 저장소 v2는 POST 고정 규약(ADR-060)이고 조건부 요청 전례가 없으며, 키 인증+KR
게이트 API라 중간 캐시 이득도 없다. 폴링량이 실증적으로 문제가 되면 별도 ADR로 재논의한다.

### D5 — 1차 스키마 변경 0건. 공개 표면은 기존 ops 테이블의 repository 사영으로 파생한다

공개 표면 = `serving_releases ⋈ dataset_snapshots` 사영(ADR-004 raw SQL repository, 외부/admin
**공용 함수**). 기준월은 읽기 시 정규화한다 — `source_set` JSONB의 실전 형태 4가지(설계
정본 §2)를 흡수하고, 정규화 불가 시 `parent_dataset_snapshot_id` 계보를 최대 5 hop 소급한다.
기준월 typed 컬럼 신설은 3중 스키마 정의(sql.py + 001_schema.sql + Alembic) + 백필 비용 대비
이득이 없어 기각한다. 공개 범위 통제는 전용 외부 DTO(`response_model` + `exclude_none`이
미선언 필드를 구조적으로 차단) + 계약 테스트로 한다.

사영 대상 원장은 **무한히 자란다**(T-291a 이후 daily delta 기준 연 ~365행; 별도로 일일 restore
drill이 `pending` 행을 매일 남기나 이는 사영의 state 필터가 배제한다). 수천 행 스캔 + 토큰
계산도 ms 미만이므로 상한 문제는 없지만, "수백 행" 같은 고정 상한을 계약 근거로 삼지 않는다.
drill의 원장 오염 정리는 T-291e에서 별도 판단한다.

### D6 — admin UI의 "관리"는 읽기 전용 관측이며, 기존 releases 표면을 확장한다

신규 admin 엔드포인트·패널을 만들지 않는다 — `GET /v1/admin/ops/releases`와 OpsPanel의 기존
releases 표가 이미 release 목록을 렌더하므로, 그 응답 DTO(`ServingRelease`)에 공용 사영 유래
필드(`version_token`, `change_type`, `reference_months`, `reference_months_mixed`)를
**additive**로 더하고 기존 표를 확장한다("중복 UI 없음" 원칙의 자기 적용). 행 상세
다이얼로그에 **외부 응답 미리보기**(trusted-proxy 경유 실제 `/v2/dataset/version` 호출 결과
렌더)와 curl 스니펫을 둔다.

미리보기의 한계를 명시한다: trusted-proxy 경로는 `require_public_api_key`를 신뢰 클라이언트로
우회하므로, 미리보기가 검증하는 것은 **응답 본문의 공개 범위**이지 인증 동작이 아니다. 인증
포함 검증은 live e2e(실제 키 발급 → 직접 호출)가 담당한다.

이력 개변·기준월 수기 정정·토큰 회전 UI는 두지 않는다 — ops는 append-only 철학(ADR-033)이고,
토큰은 파생값이라 회전할 실체가 없다. 키 수명주기는 기존 SettingsPanel이 담당한다.

## 결과

### 엣지 케이스별 거동 (계약, T-291a 이후 기준)

| 시나리오 | 원장/토큰 | 외부 API 거동 |
|---|---|---|
| full_load / manual_rebuild / (T-291a 이후) CLI refresh swap·postload execute_safe | 새 release → 새 토큰 | `changed:true`, `full`. 동일 데이터 재적재도 새 토큰(허용된 과잉 감지) |
| daily_delta (T-291a의 라벨링 이후) | 새 release → 새 토큰 | `changed:true`, `delta` → 소비자는 증분 갱신 |
| restore `new_database`(hot-swap 미실행) | `pending` 행만 **라이브** 원장에 추가 | 서빙 미변경 — 사영이 `pending`을 배제하므로 토큰·응답 불변 (정상) |
| restore `replace_current` | (T-291a 이후) active `restore` 행 기록 → 새 토큰 | `changed:true`, `full`. 현재 코드는 `pending`만 남겨 토큰이 안 바뀌는 거짓 음성 — D0의 수정 대상 |
| hot-swap restore(ADR-036) | 교체 DB 원장 = 백업 시점 이력 + restore 신규 active 행. 백업~복원 사이 릴리스 소멸 | 새 토큰, `full`. 소비자 저장 토큰이 소멸분이면 `known_version_found:false` → 전체 재동기화 |
| hot-swap smoke 실패 자동 원복 | 짧게 교체 DB가 서빙된 뒤 원복. **어느 쪽 원장에도 새 행 없음**(감사 로그만) | 그 창에서 폴링한 소비자는 토큰이 T1→T0→T1로 일시 요동 — 과잉 재동기화 1회로 수렴, 계약 위반 아님 |
| hot-swap rollback(원 DB 복귀) | 이전 원장 복귀 + `rollback` 신규 active 행 | 새 토큰, `full`. 과거 토큰들이 history에 재등장하나 active는 항상 신규 행 → 계약 무변화 |
| `/v1/admin/ops/releases/{id}/rollback` | source match set 교체만 — release 행도 서빙 객체도 불변 | 서빙 전환이 아니므로 토큰 불변 (이후 재적재/refresh 시점에 감지) |
| 이력 리셋 / DB 재구축 | 원장 신규 시작 | UUID 파생이라 연속성 요구 자체가 없다. `known_version_found:false`/`since_found:false` → 전체 재동기화 |
| active 0건 | active 행 없음 | `available:false`, HTTP 200 (오류 아님) |
| active 다중 | DB가 봉쇄 — `idx_ops_serving_releases_one_active` partial unique index(T-049)가 active ≤ 1을 강제 | 도달 불가 |
| pending / failed / (미기록 상태) | `rolled_back`은 enum에만 있고 현재 어떤 코드도 쓰지 않는다(전이는 active→superseded뿐) | `pending`/`failed`는 외부 표면 어디에도 출현하지 않음. 사영 필터는 `rolled_back`을 방어적으로 포함하되 계약은 이에 의존하지 않음 |
| 기준월 역행 | restore 후 가능 | 허용 — `reference_months`는 비단조로 명문화, 변경 신호는 토큰뿐 |

이력 보존은 **보증하지 않는다** — 복원 시 백업 이후 이력이 소멸할 수 있다.

### 하지 않는 것 (비목표)

1. 단조 공개 버전 번호·epoch·원장 테이블 (D1 기각 사유).
2. GET+ETag/If-None-Match/304 (D4). 폴링량 실증 시 별도 ADR.
3. webhook/push — 폴링으로 충분. 백업 callback webhook은 운영자용으로 별개.
4. `source_set_hash`·`mv_hash`·내부 UUID·`row_counts`·스택 버전 외부 노출 — 부적격 신호이거나
   fingerprinting 재료.
5. 백업 정보 외부 노출 일체 — admin 전용.
6. MV 내용 해시 — 전 행 스캔 비용 대비, release grain 토큰이 이미 (D0 성립 시) 거짓 음성 없는
   신호.
7. v1 표면·healthz/readyz 버전 노출 — v1 동결(ADR-038), readyz는 keyless.
8. Python 라이브러리 공개 메서드 — REST 전용(ADR-039).
9. 키 스코프·per-key rate limit — 전용 admission scope(D3) + TTL 캐시 + 키 회수로 시작.
   ADR-064 스코프 도입 시 재검토.
10. 이력 편집·note·기준월 수기 정정·토큰 회전 UI (D6).
11. 1차 스키마 변경(컬럼·뷰·시퀀스·인덱스·Alembic 0건).
12. `change_type: "revert"` — D2 기각 사유. additive 재도입 후보.

## 후속

- T-291a(서빙 전환 기록 완결)가 외부 공개의 선행 조건 — D0.
- ADR-064에 키 스코프가 도입되면 이 표면의 스코프 분리 재검토.
- `serving_releases`의 기존 `notes` 컬럼을 admin 표면에 노출할지 별도 판단(신규 컬럼 아님).
- GET+ETag 조건부 요청 재논의(폴링량 실증 시).
- restore drill의 원장 `pending` 행 누적(연 ~365행) 정리 — T-291e.
