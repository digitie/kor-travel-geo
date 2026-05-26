# T-045: 원천 자료 기준월 선택과 대용량 업로드/적재 UX

## 구현 상태

- 상태: 구현 완료
- 구현 브랜치: `codex/t045-source-set-load-ux`
- 기준 ADR: ADR-029
- 주요 파일:
  - 백엔드 DTO: `src/kraddr/geo/dto/admin.py`
  - source set 탐지/계획: `src/kraddr/geo/infra/source_set.py`
  - upload set 저장소: `src/kraddr/geo/infra/uploads.py`
  - REST: `src/kraddr/geo/api/routers/admin.py`
  - 라이브러리: `src/kraddr/geo/client.py`
  - CLI: `src/kraddr/geo/cli/main.py`
  - UI: `kraddr-geo-ui/components/admin/LoadConsole.tsx`
  - UI 상태 helper: `kraddr-geo-ui/lib/load-workflow.ts`
  - 테스트: `tests/unit/test_source_set_plan.py`, `kraddr-geo-ui/tests/unit/load-workflow.test.ts`

## 배경

도로명주소 관련 원천은 같은 기관에서 제공되더라도 배포 주기와 업데이트 시점이 다르다. 실제 로컬 자료에서도 다음처럼 기준월이 섞여 있었다.

| 원천 | 예시 기준월 | 비고 |
|------|-------------|------|
| 도로명주소 한글_전체분 | `202603` | 건물 단위 주소 정본 |
| 위치정보요약DB_전체분 | `202604` | 출입구 좌표 |
| 내비게이션용DB_전체분 | `202604` | centroid/진입점 |
| 도로명주소 전자지도 SHP | `202604` | 행정/건물/도로 도형 |
| 도로명주소 출입구 정보 | `202605` | direct `bd_mgt_sn + EPSG:5179` 출입구 |
| 상세주소 동/구역 추가 레이어 | `202605` | 별도 overlay/분석 후보 |

따라서 `full_load_batch`가 단일 `--yyyymm` 값을 모든 child에 강제로 적용하면 두 문제가 생긴다.

1. 실제로는 다른 기준월인 자료를 같은 기준월로 기록해 정합성 C10과 운영 감사가 부정확해진다.
2. 운영자가 의도적으로 최신 출입구 자료를 섞어 쓰려는 상황과, 실수로 다른 월을 골라 적재하는 상황을 구분할 수 없다.

T-045는 이 문제를 해결하기 위해 원천 묶음(`source_set`)을 명시적인 계획 객체로 만들고, CLI/API/라이브러리/UI에서 사용자가 의도한 방식대로 진행하도록 UX 계약을 구현했다. 현재 구현은 source set 탐지, 기준월 확인 token, persistent upload set, REST/라이브러리/CLI, `/admin/load` UI의 다중 파일 업로드와 full-load batch 등록까지 포함한다.

## 결정 요약

1. 기준월은 원천별로 독립된 값이다. `juso_yyyymm`, `parcel_link_yyyymm`, `locsum_yyyymm`, `navi_yyyymm`, `shp_yyyymm`, `roadaddr_entrance_yyyymm`, `sppn_makarea_yyyymm`처럼 별도 필드로 기록한다.
2. CLI는 발견된 기준월이 서로 다르면 즉시 진행하지 않고, 사람이 의도한 혼합 적재인지 확인한다.
3. API/라이브러리는 prompt를 띄우지 않는다. 대신 디렉터리를 읽어 후보를 매칭하는 함수와, 각 원천의 기준월/경로를 명시해서 적재 계획을 만드는 함수를 분리한다.
4. UI는 파일 선택 또는 업로드 완료 후 source set을 분석하고, 기준월이 맞지 않으면 확인 팝업을 띄운다. 사용자가 계속 진행을 명시하면 그 확인 사실을 batch payload에 남긴다.
5. 대용량 적재는 `업로드 → 파일 저장 완료 → 적재 시작` 순서로만 진행한다. 업로드와 적재의 진행률은 별도 퍼센트로 표시하고, 둘 다 중간 취소가 가능해야 한다.

## 구현 요약

### Source kind와 child job 매핑

구현된 source kind는 다음 순서로 처리한다.

| source kind | 필수 | child job | 비고 |
|-------------|------|-----------|------|
| `juso` | 예 | `juso_text_load` | 도로명주소 한글 전체분. `도로명주소 한글`, `rnaddrkor` 파일명으로 탐지한다. |
| `parcel_link` | 예 | `juso_parcel_link_load` | 같은 도로명주소 한글 전체분 또는 `jibun_rnaddrkor` 파일로 탐지한다. 도로명주소 전체분 디렉터리는 `juso`와 `parcel_link` 후보를 함께 만든다. |
| `locsum` | 예 | `locsum_load` | 위치정보요약DB, `locsum`, `entrc` 이름으로 탐지한다. |
| `navi` | 예 | `navi_load` | 내비게이션용DB, `navi` 이름으로 탐지한다. |
| `shp` | 예 | `shp_polygons_load` | 전자지도 SHP 디렉터리 또는 `TL_SPBD_BULD.shp` 부모 디렉터리를 후보로 둔다. child payload에는 `mode="full"`을 넣는다. |
| `roadaddr_entrance` | 아니오 | `roadaddr_entrance_load` | `RNENTDATA_*` 또는 `출입구` 이름으로 탐지한다. |
| `sppn_makarea` | 아니오 | 없음 | ADR-027/T-042 구현 전까지 source set metadata에는 남기되 child job은 만들지 않는다. |
| `pobox` | 아니오 | `pobox_load` | 사서함/우편번호 보조 자료. 명시적으로 선택된 경우에만 child job이 된다. |
| `bulk` | 아니오 | `bulk_load` | 다량배달처 보조 자료. 명시적으로 선택된 경우에만 child job이 된다. |

기준월 추론은 경로의 마지막 4개 part에서 `YYYYMM`을 먼저 찾고, 없으면 파일명에서 `YYMM`을 찾아 `20YYMM`으로 보정한다. 예를 들어 `RNENTDATA_2605_11.txt`는 `202605`로 해석한다.

### Plan payload

`build_full_load_source_set_plan()`은 `full_load_batch` 등록에 사용할 `batch_payload`를 만든다. 새 구현은 기존 `payloads` mapping 대신 명시적인 `children` 배열을 사용한다. 이 방식은 optional source가 빠졌을 때 `pobox_load` 같은 기본 child가 빈 payload로 생성되는 문제를 피하고, `roadaddr_entrance_load`처럼 후속에 추가된 child도 정합성 gate가 기다릴 수 있게 한다.

`batch_payload.source_set`에는 다음 감사 필드가 들어간다.

| 필드 | 의미 |
|------|------|
| `source_set_id` | 기준월과 후보 경로 기반의 짧은 해시가 붙은 식별자 |
| `yyyymm_by_kind` | source kind별 기준월 |
| `mixed_yyyymm` | 기준월이 2개 이상인지 여부 |
| `mixed_yyyymm_acknowledged` | 혼합 기준월 확인 token이 검증됐는지 여부 |
| `acknowledged_by` / `acknowledged_at` | 확인 주체와 시각 |
| `confirmation_token_hash` | 원문 확인 문구를 저장하지 않기 위한 SHA-256 hash |
| `candidate_paths` | 선택된 후보 경로 |
| `candidate_sha256` | 파일 또는 디렉터리 inventory fingerprint |

### 혼합 기준월 확인 token

혼합 기준월인 경우 서버와 UI/CLI가 같은 규칙으로 확인 문구를 만든다.

```text
<정렬된 기준월 목록을 "/"로 연결> 혼합 적재 확인
```

예: `juso=202603`, `locsum=202604`, `roadaddr_entrance=202605`이면 `202603/202604/202605 혼합 적재 확인`이다. API와 라이브러리는 prompt를 띄우지 않고, 이 문구가 정확히 들어온 경우에만 plan 생성을 허용한다.

## 용어

| 용어 | 의미 |
|------|------|
| source kind | `juso`, `parcel_link`, `locsum`, `navi`, `shp`, `roadaddr_entrance`, `sppn_makarea` 같은 원천 종류 |
| source candidate | 디렉터리 또는 업로드 묶음에서 발견한 개별 원천 후보. 경로, 추론 기준월, 시도 범위, 파일 수, checksum을 가진다 |
| source set | full-load 한 번에 사용할 원천 후보들의 선택 결과 |
| source set plan | 사용자가 실제로 적재할 경로와 기준월, 기준월 불일치 여부, 확인 여부, child job payload를 포함한 계획 객체 |
| mixed yyyymm | source set 안의 기준월이 모두 같지 않은 상태 |
| confirmation token | 기준월 불일치 상태를 사람이 확인했음을 서버가 재검증할 수 있게 하는 짧은 해시 또는 문자열 |

## 백엔드/라이브러리 함수 분리

### 디렉터리 발견 함수

디렉터리 또는 업로드 세션 경로를 읽어 원천 후보를 자동 매칭한다.

```python
def discover_load_sources(
    root_path: Path,
    *,
    include_optional: bool = True,
) -> SourceSetDiscovery: ...
```

반환 DTO 예시:

```python
class SourceCandidate(FrozenModel):
    kind: Literal[
        "juso",
        "parcel_link",
        "locsum",
        "navi",
        "shp",
        "roadaddr_entrance",
        "sppn_makarea",
    ]
    path: str
    inferred_yyyymm: str | None
    sido_count: int | None = None
    file_count: int | None = None
    byte_size: int | None = None
    sha256: str | None = None
    confidence: Literal["high", "medium", "low"]
    note: str | None = None

class SourceSetDiscovery(FrozenModel):
    root_path: str
    candidates: tuple[SourceCandidate, ...]
    recommended: dict[str, SourceCandidate]
    missing_required: tuple[str, ...]
    mixed_yyyymm: bool
    yyyymm_by_kind: dict[str, str | None]
    warning: str | None = None
```

이 함수는 적재를 시작하지 않는다. UI와 CLI가 사용자에게 보여 줄 후보 테이블을 만드는 데만 사용한다. `AsyncAddressClient.discover_load_sources()`는 같은 helper를 async public method 형태로 감싼다.

### 명시 기준월 계획 함수

사용자가 각 원천의 기준월 또는 경로를 명시했을 때만 실제 적재 계획을 만든다.

```python
def build_full_load_source_set_plan(
    *,
    root_path: Path | None = None,
    versions: dict[str, str] | None = None,
    explicit_paths: dict[str, str] | None = None,
    include_optional: bool = True,
    allow_mixed_yyyymm: bool = False,
    confirmation_token: str | None = None,
    acknowledged_by: str = "api",
) -> SourceSetPlan: ...
```

규칙:

- `root_path`가 있으면 기준월별 디렉터리/ZIP 이름을 찾아 후보를 고른다.
- `explicit_paths`가 있으면 경로를 우선한다. 이때도 파일명 또는 member명에서 추론 가능한 기준월을 계산하고, 사용자가 입력한 기준월과 다르면 `warning`으로 노출한다.
- 필수 원천은 `juso`, `parcel_link`, `locsum`, `navi`, `shp`다. `roadaddr_entrance`, `sppn_makarea`는 선택 원천이다.
- `allow_mixed_yyyymm=False`인데 기준월이 서로 다르면 계획 생성은 실패한다.
- `allow_mixed_yyyymm=True`인 경우에도 `confirmation_token` 또는 CLI 대화 확인이 있어야 실제 `full_load_batch` 등록으로 넘어간다.
- 계획에는 child job payload가 포함되지만, 이 함수 자체는 큐에 job을 만들지 않는다.
- `AsyncAddressClient.build_full_load_source_set_plan()`은 같은 helper를 async public method 형태로 감싼다.

### 큐 등록 함수

계획이 확정된 뒤에만 batch를 등록한다.

```python
async def submit_full_load_source_set(
    plan: SourceSetPlan,
) -> LoadJobStatus: ...
```

`SourceSetPlan`은 `load_jobs.payload.source_set`과 `load_manifest.source_set`에 그대로 남겨야 한다. 특히 다음 필드는 운영 감사에 필수다.

- `yyyymm_by_kind`
- `mixed_yyyymm`
- `mixed_yyyymm_acknowledged`
- `acknowledged_by`
- `acknowledged_at`
- `confirmation_token_hash`
- `candidate_paths`
- `candidate_sha256`

## CLI UX

### 자동 발견 모드

```bash
kraddr-geo load full-set ./data/juso
```

동작:

1. `discover_load_sources()`를 실행한다.
2. 원천별 후보와 기준월을 표로 출력한다.
3. 필수 원천이 빠져 있으면 적재하지 않고 종료한다.
4. 기준월이 모두 같으면 `build_full_load_source_set_plan(..., allow_mixed_yyyymm=False)` 후 적재를 시작한다.
5. 기준월이 다르면 아래와 같은 확인 프롬프트를 띄운다.

```text
원천 자료 기준월이 서로 다릅니다.

  juso                 202603  ./data/juso/202603_도로명주소 한글_전체분
  parcel_link          202603  ./data/juso/202603_도로명주소 한글_전체분
  locsum               202604  ./data/juso/202604_위치정보요약DB_전체분.zip
  navi                 202604  ./data/juso/202604_내비게이션용DB_전체분
  shp                  202604  ./data/juso/도로명주소 전자지도
  roadaddr_entrance    202605  ./data/juso/도로명주소 출입구 정보

의도적으로 혼합 기준월 적재를 진행하려면 다음 문구를 그대로 입력하십시오:
202603/202604/202605 혼합 적재 확인
>
```

확인 문구가 틀리거나 빈 입력이면 적재하지 않는다. 비대화형 환경에서는 prompt를 띄우지 않고 실패한다.

### 명시 기준월 모드

```bash
kraddr-geo load full-set ./data/juso \
  --juso-yyyymm 202603 \
  --parcel-link-yyyymm 202603 \
  --locsum-yyyymm 202604 \
  --navi-yyyymm 202604 \
  --shp-yyyymm 202604 \
  --roadaddr-entrance-yyyymm 202605 \
  --allow-mixed-yyyymm \
  --confirm-source-set "202603/202604/202605 혼합 적재 확인"
```

규칙:

- 명시 기준월 모드는 자동 발견보다 우선한다.
- `--allow-mixed-yyyymm` 없이 기준월이 다르면 실패한다.
- CI나 cron에서는 `--confirm-source-set`을 반드시 요구한다. `--yes` 같은 포괄 옵션만으로는 기준월 불일치를 승인하지 않는다.
- 단일 `--yyyymm`은 새 full-set 명령에서 deprecated로 둔다. 기존 개별 로더(`load juso`, `load locsum`, `load shp`)의 `--yyyymm`은 유지한다.

## REST API 설계

기존 `/v1/admin/loads`는 큐 등록 표면으로 유지한다. source set 분석과 계획 수립은 별도 엔드포인트로 분리한다.

```text
POST /v1/admin/load-sources/discover
  body: { "root_path": "...", "include_optional": true }
  res:  SourceSetDiscovery

POST /v1/admin/load-sources/plan
  body: {
    "root_path": "...",
    "versions": {
      "juso": "202603",
      "parcel_link": "202603",
      "locsum": "202604",
      "navi": "202604",
      "shp": "202604",
      "roadaddr_entrance": "202605"
    },
    "allow_mixed_yyyymm": true,
    "confirmation_token": "..."
  }
  res: SourceSetPlan

POST /v1/admin/loads
  body: { "kind": "full_load_batch", "payload": SourceSetPlan.batch_payload }
```

API는 prompt를 띄우지 않는다. UI가 팝업으로 확인을 받은 뒤 `confirmation_token`을 포함해 계획을 만들고 큐에 등록한다.

## 업로드 UX와 API

적재는 오래 걸리므로 UI는 파일을 고르자마자 적재를 시작하지 않는다. 반드시 모든 파일이 서버에 저장되고 checksum/기준월 추론이 끝난 뒤에만 적재 등록 버튼을 활성화한다.

### 업로드 단계

요구사항:

- 다중 파일 선택 지원
- drag and drop 지원
- ZIP, TXT, SHP bundle 같은 여러 파일을 한 upload set으로 묶음
- 파일별 업로드 퍼센트 표시
- 전체 업로드 퍼센트 표시
- 업로드 중 개별 파일 또는 전체 업로드 취소 가능
- 업로드 실패 파일은 재시도 가능
- 업로드 완료 후 서버가 저장 경로, 크기, checksum, 추론 기준월, source kind 후보를 반환

권장 API:

```text
POST /v1/admin/uploads
  body: { "purpose": "full_load_source_set" }
  res:  { "upload_set_id": "..." }

PUT /v1/admin/uploads/{upload_set_id}/files?filename=...&relative_path=...
  raw body stream
  res: UploadFileStatus

GET /v1/admin/uploads/{upload_set_id}
  res: UploadSetStatus

POST /v1/admin/uploads/{upload_set_id}/cancel
  res: UploadSetStatus

POST /v1/admin/load-sources/discover
  body: { "upload_set_id": "..." }
  res: SourceSetDiscovery
```

브라우저 업로드 진행률은 `fetch`만으로 안정적으로 얻기 어렵다. UI 구현 시에는 `XMLHttpRequest.upload.onprogress` 또는 동등한 업로드 progress 지원 wrapper를 사용한다. 서버는 저장 중 partial file을 `*.part`로 두고, 완료 시 checksum 확인 후 원래 이름으로 atomic rename한다.

### 기준월 확인 팝업

파일 선택 또는 업로드 완료 후 `SourceSetDiscovery.mixed_yyyymm=True`이면 UI는 적재 시작 전에 modal을 띄운다.

팝업 내용:

- 원천별 기준월 표
- 필수 원천 누락 여부
- 선택 원천이 기본 full-load에 포함되는지 여부
- C10 정합성 리포트에 기준월 혼합이 남는다는 설명
- 계속 진행 버튼과 취소 버튼

계속 진행 버튼은 단순 확인 checkbox 하나만으로 충분하지 않다. 실수 방지를 위해 UI는 서버가 내려준 확인 문구 또는 token을 다시 제출한다.

### 적재 단계

업로드가 모두 끝나고 source set plan이 확정되면 `POST /v1/admin/loads`로 `full_load_batch`를 등록한다.

화면은 두 종류의 진행률을 분리해서 보여 준다.

| 구분 | 계산 방식 | 취소 |
|------|-----------|------|
| 업로드 진행률 | 브라우저가 보낸 byte / 총 byte | `AbortController` 또는 XHR abort, 서버 upload set cancel |
| 적재 진행률 | `load_jobs.progress`와 child job 진행률 가중 평균 | `POST /v1/admin/loads/{job_id}/cancel` |

적재 취소는 root job에 대해 실행한다. 서버는 root와 같은 `load_batch_id`를 가진 `queued` child를 `cancelled`로 바꾸고, 실행 중 child에는 협조적 cancel event를 전달한다.

## 정합성/감사 기록

C10은 더 이상 단순히 "모든 source_yyyymm이 같은가"만 보지 않는다.

- `mixed_yyyymm=False`이면 기존처럼 OK/WARN/ERROR를 계산한다.
- `mixed_yyyymm=True`이고 `mixed_yyyymm_acknowledged=True`이면 C10은 `INFO` 또는 `WARN`으로 남기되, 운영자가 의도적으로 혼합했다는 `note`를 포함한다.
- `mixed_yyyymm=True`인데 확인 기록이 없으면 `ERROR`로 본다.
- 정합성 sample에는 `yyyymm_by_kind`와 `acknowledged_by`를 포함한다.

## 테스트 및 검증

구현 테스트:

| 항목 | 테스트 |
|------|--------|
| 디렉터리 scan | `tests/unit/test_source_set_plan.py::test_source_set_discovery_matches_required_sources_and_mixed_months` |
| 업로드 부모 경로 날짜 오인 방지 | `tests/unit/test_source_set_plan.py::test_infer_yyyymm_prefers_nearest_file_or_directory_name` |
| optional 제외 | `tests/unit/test_source_set_plan.py::test_source_set_discovery_can_exclude_optional_sources` |
| 같은 기준월 plan | `tests/unit/test_source_set_plan.py::test_source_set_plan_builds_single_month_batch_without_confirmation` |
| 혼합 기준월 거절/승인 | `tests/unit/test_source_set_plan.py::test_source_set_plan_requires_explicit_mixed_confirmation` |
| upload set 저장/취소 | `tests/unit/test_source_set_plan.py::test_upload_set_stores_files_safely_and_can_be_cancelled` |
| 업로드 크기 제한 실패 | `tests/unit/test_source_set_plan.py::test_upload_set_marks_failed_file_when_size_limit_is_exceeded` |
| REST route 노출 | `tests/unit/test_api_app_contract.py::test_create_app_exposes_expected_routes_without_starting_lifespan` |
| CLI full-set 노출/확인 문구 | `tests/unit/test_cli_contract.py::test_cli_exposes_t018_operational_commands`, `tests/unit/test_cli_contract.py::test_full_set_command_requires_specific_mixed_confirmation` |
| batch DAG successor | `tests/unit/test_infra_repo_sql.py::test_job_queue_batch_successors_wait_for_all_source_children` |
| UI 상태 전이/token/progress | `kraddr-geo-ui/tests/unit/load-workflow.test.ts` |

검증 명령:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_source_set_plan.py tests/unit/test_api_app_contract.py tests/unit/test_client_submit_load_batch.py tests/unit/test_infra_repo_sql.py -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kraddr/geo tests/unit/test_source_set_plan.py tests/unit/test_api_app_contract.py tests/unit/test_client_submit_load_batch.py tests/unit/test_infra_repo_sql.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo
cd kraddr-geo-ui && env "PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH" npm run lint
cd kraddr-geo-ui && env "PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH" npm run type-check
cd kraddr-geo-ui && env "PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH" npm run test -- load-workflow
```

## 남은 후속 범위

- C10 정합성은 `source_set`의 `mixed_yyyymm_acknowledged`와 `acknowledged_by`를 더 세밀하게 읽어 INFO/WARN/ERROR를 조정할 수 있다. 현재 구현은 batch payload에 감사 필드를 남기는 단계까지 완료했다.
- `ops.dataset_snapshots`에 source set 확정 정보를 자동으로 연결하는 작업은 T-027/T-047의 full-load gate 보강과 함께 진행한다.
- 업로드 세션은 JSON manifest 기반 local filesystem registry다. 여러 API 인스턴스가 같은 upload set을 다뤄야 하는 배포라면 공유 파일시스템 또는 object storage manifest backend가 필요하다.
- UI의 대용량 업로드는 브라우저 XHR progress를 사용한다. 파일별 재시도 버튼과 새로고침 후 업로드 진행률 복구는 후속 개선으로 남긴다.
