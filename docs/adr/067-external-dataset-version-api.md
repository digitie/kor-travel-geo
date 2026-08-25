# ADR-067: 데이터셋 버전 외부 공개는 serving release 파생 opaque 토큰 + 최소 공개 원칙으로 한다

- 상태: proposed
- 날짜: 2026-08-26
- 결정자: human 요청, claude 설계
- 관련: ADR-033(ops 스키마)·ADR-036(hot-swap restore)·ADR-037(GeoIP gate)·ADR-038(v1/v2 분리)·
  ADR-039(라이브러리 공개 범위)·ADR-060(v2 규약)·ADR-061(구조화 400)·ADR-064(공개 API key)
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

## 결정

### D1 — 버전 토큰은 active serving release에서 파생한 opaque 토큰으로 한다. 신규 저장 없음

```
version_token = "dv1-" + sha256("ktg.dataset.version:" + serving_release_id)[:32]   # hex 32자
```

모든 서빙 전환(full_load/daily_delta/restore/manual_rebuild/rollback)은
`ops.serving_releases`에 새 행을 만든다(ADR-017/ADR-036의 불변식 — 본 ADR이 외부 계약의 기반
불변식으로 명문화한다). `serving_release_id`는 uuid4이므로 파생 토큰은 이력 리셋·복원 후에도
재사용되지 않는다.

계약의 전부는 다음 한 문장이다: **토큰이 같으면 서빙 데이터셋이 바뀌지 않았다. 역은 보증하지
않는다**(동일 데이터 재적재·rollback도 새 토큰 = 허용된 과잉 감지). 토큰은 불투명 값으로,
동등 비교만 허용하고 파싱·정렬은 계약 위반이다.

기각한 대안:

- **epoch + 단조 seq 신규 원장 테이블** — hot-swap restore가 원장 테이블 자체를 백업 시점으로
  되돌린다. 백업 시점 seq=40, 라이브 seq=43 상태에서 복원하면 다음 발급이 41이 되어 같은 epoch
  안에서 토큰이 재사용된다. epoch 값이 스왑되는 DB 안에 있는 한 구조적으로 방어할 수 없고,
  "토큰 영구 비재사용" 보증이 거짓 약속이 된다. 테이블 2개·트리거·백필 비용은 덤이다.
- **`serving_release_id` 원값 노출** — 동작은 같지만 내부 핸들이 외부 계약에 결합된다. 파생
  1줄로 차단할 수 있는 결합이다.
- **`source_set_hash` / `mv_hash` 재사용** — 전자는 스냅샷 생성 경로(batch/추론/manifest 복사)
  별로 형상이 달라 같은 데이터에 다른 해시, 다른 데이터에 같은 해시가 모두 가능하다. 후자는
  MV 정의+행수 수준이라 데이터 변경의 ground truth가 아니다.

### D2 — 외부 공개 필드는 4개뿐이다

`version_token`, `activated_at`, `change_type`(coarse 3종: `full`/`delta`/`revert`),
`reference_months`(원천별 YYYYMM map) + `reference_months_mixed`.

- `change_type` 매핑: `full_load|restore|manual_rebuild → "full"`, `daily_delta → "delta"`,
  `rollback → "revert"`. 소비자의 행동 공간이 재동기화 3종뿐이므로 `release_kind` 5종 원값을
  노출하지 않는다(운영 빈도·복원 사실의 유출이기도 하다).
- 기준월은 원천별 map으로 공개한다 — 혼합 기준월이 정상 상태이므로 대표값 하나로 뭉개지
  않는다. 도출 불가 시 필드를 생략하고(exclude_none), 그 경우 토큰만이 신뢰 신호라는 규약을
  문서화한다.
- 내부 UUID·`source_set_hash`·`mv_hash`·`row_counts`·git/alembic/PostgreSQL 버전·`source_set`
  원본, 그리고 **백업 관련 정보 일체**(존재·시각·artifact id·sha256)는 비공개다.

### D3 — 인증·게이트는 기존 것을 재사용한다

`require_public_api_key`(ADR-064) 그대로, 키 스코프 신설 없음. GeoIP KR 게이트(ADR-037)는
전역 적용을 그대로 받는다(`geoip_open_paths` 미추가). 버전 메타데이터는 같은 키로 접근 가능한
주소 데이터 본체보다 민감하지 않고, trusted-proxy 경유로 admin UI 미리보기가 추가 비용 없이
가능해진다.

### D4 — API 형태는 v2 POST 고정 + body 조건부 폴링으로 한다

`POST /v2/dataset/version`(요청 body `known_version` → 응답 `changed`/`known_version_found`)과
`POST /v2/dataset/history`(`since_version`/`limit`/opaque `cursor`). GET+ETag/304 조건부 요청은
기각 — 이 저장소 v2는 POST 고정 규약(ADR-060)이고 조건부 요청 전례가 없으며, 키 인증+KR
게이트 API라 중간 캐시 이득도 없다. 폴링량이 실증적으로 문제가 되면 별도 ADR로 재논의한다.

### D5 — 1차 스키마 변경 0건. 공개 표면은 기존 ops 테이블의 repository 사영으로 파생한다

공개 표면 = `serving_releases ⋈ dataset_snapshots` 사영(ADR-004 raw SQL repository, 외부/admin
**공용 함수**). 기준월은 읽기 시 정규화한다 — `source_set`의 3가지 실전 형태(rebuild 형태 A /
추론·manifest 형태 B / 빈 값 형태 C)를 흡수하고, 형태 C는 `parent_dataset_snapshot_id` 계보를
최대 5 hop 소급해 최초 정규화 가능한 `source_set`을 채택한다. 원장이 수백 행 이하라 읽기
정규화 비용은 무시 가능하고, 기준월 typed 컬럼 신설은 3중 스키마 정의(sql.py + 001_schema.sql
+ Alembic) + 백필 비용 대비 이득이 없어 기각한다. 공개 범위 통제는 전용 외부
DTO(`response_model` + `exclude_none`이 미선언 필드를 구조적으로 차단) + 계약 테스트로 한다.

### D6 — admin UI의 "관리"는 읽기 전용 관측이다

`/admin/ops`에 데이터셋 버전 패널(목록·행 상세·**외부 응답 미리보기**·curl 스니펫)을 추가한다.
미리보기는 trusted-proxy 경유 실제 `/v2/dataset/version` 호출 결과를 렌더해, 공개 범위 회귀를
운영자가 눈으로 잡는 보안 리뷰 표면을 겸한다. 이력 개변·기준월 수기 정정·토큰 회전 UI는 두지
않는다 — ops는 append-only 철학(ADR-033)이고, 토큰은 파생값이라 회전할 실체가 없다. 키
수명주기는 기존 SettingsPanel이 담당하며 중복 UI를 만들지 않는다.

## 결과

### 엣지 케이스별 거동 (계약)

| 시나리오 | 원장/토큰 | 외부 API 거동 |
|---|---|---|
| full_load / daily_delta / manual_rebuild | 새 release → 새 토큰 | `changed:true`, `full`/`delta`. 동일 데이터 재적재도 새 토큰(허용된 과잉 감지) |
| restore(일반/hot-swap, ADR-036) | 교체 DB 원장 = 백업 시점 이력 + restore 신규 행. 백업~복원 사이 릴리스 소멸 | 새 토큰(uuid4 파생 — 재사용 불가), `full`. 소비자 저장 토큰이 소멸분이면 `known_version_found:false` → 전체 재동기화 |
| rollback | rollback 신규 행 active, 이전 rolled_back | 새 토큰, `revert`. 내용이 같아도 토큰은 전진한다 |
| hot-swap rollback(원 DB 복귀) | 이전 원장 복귀 + rollback 신규 행 | 과거 토큰들이 history에 재등장하나 active는 항상 신규 행 → 계약 무변화 |
| 이력 리셋 / DB 재구축 | 원장 신규 시작 | UUID 파생이라 연속성 요구 자체가 없다. `known_version_found:false`/`since_found:false` → 전체 재동기화 |
| active 0건 | active 행 없음 | `available:false`, HTTP 200 (오류 아님) |
| active 다중 | DB가 봉쇄 — `idx_ops_serving_releases_one_active` partial unique index(T-049)가 active ≤ 1을 강제 | 사영의 `ORDER BY ordered_at DESC, id DESC` tiebreak는 방어적 관성일 뿐 도달 불가 |
| pending / failed | 활성화된 적 없음 | 외부 표면 어디에도 출현하지 않음 |
| 기준월 역행 | restore 후 가능 | 허용 — `reference_months`는 비단조로 명문화, 변경 신호는 토큰뿐 |

이력 보존은 **보증하지 않는다** — 복원 시 백업 이후 이력이 소멸할 수 있다.

### 하지 않는 것 (비목표)

1. 단조 공개 버전 번호·epoch·원장 테이블 (D1 기각 사유).
2. GET+ETag/If-None-Match/304 (D4). 폴링량 실증 시 별도 ADR.
3. webhook/push — 폴링으로 충분. 백업 callback webhook은 운영자용으로 별개.
4. `source_set_hash`·`mv_hash`·내부 UUID·`row_counts`·스택 버전 외부 노출 — 부적격 신호이거나
   fingerprinting 재료.
5. 백업 정보 외부 노출 일체 — admin 전용.
6. MV 내용 해시 — 전 행 스캔 비용 대비, release grain 토큰이 이미 거짓 음성 없는 신호.
7. v1 표면·healthz/readyz 버전 노출 — v1 동결(ADR-038), readyz는 keyless.
8. Python 라이브러리 공개 메서드 — REST 전용(ADR-039).
9. 키 스코프·per-key rate limit·전용 admission scope — 전역 `/v2` semaphore + TTL 캐시 + 키
   회수로 충분.
10. 이력 편집·note·기준월 수기 정정·토큰 회전 UI (D6).
11. 1차 스키마 변경(컬럼·뷰·시퀀스·인덱스·Alembic 0건).

### 후속 open

- ADR-064에 키 스코프가 도입되면 이 표면의 스코프 분리 재검토.
- `serving_releases.external_note`(운영자 주석) 컬럼 별도 판단.
- GET+ETag 조건부 요청 재논의(폴링량 실증 시).
- `equivalent_version_token`(rollback 내용 동등 포인터) — additive 후보.
