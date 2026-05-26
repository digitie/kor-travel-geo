# T-045: 원천 자료 기준월 선택과 대용량 업로드/적재 UX 설계

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

T-045는 이 문제를 해결하기 위해 원천 묶음(`source_set`)을 명시적인 계획 객체로 만들고, CLI/API/라이브러리/UI에서 사용자가 의도한 방식대로 진행하도록 UX 계약을 정의한다. 본 문서는 구현 전 설계 문서이며, 코드는 아직 작성하지 않는다.

## 결정 요약

1. 기준월은 원천별로 독립된 값이다. `juso_yyyymm`, `parcel_link_yyyymm`, `locsum_yyyymm`, `navi_yyyymm`, `shp_yyyymm`, `roadaddr_entrance_yyyymm`, `sppn_makarea_yyyymm`처럼 별도 필드로 기록한다.
2. CLI는 발견된 기준월이 서로 다르면 즉시 진행하지 않고, 사람이 의도한 혼합 적재인지 확인한다.
3. API/라이브러리는 prompt를 띄우지 않는다. 대신 디렉터리를 읽어 후보를 매칭하는 함수와, 각 원천의 기준월/경로를 명시해서 적재 계획을 만드는 함수를 분리한다.
4. UI는 파일 선택 또는 업로드 완료 후 source set을 분석하고, 기준월이 맞지 않으면 확인 팝업을 띄운다. 사용자가 계속 진행을 명시하면 그 확인 사실을 batch payload에 남긴다.
5. 대용량 적재는 `업로드 → 파일 저장 완료 → 적재 시작` 순서로만 진행한다. 업로드와 적재의 진행률은 별도 퍼센트로 표시하고, 둘 다 중간 취소가 가능해야 한다.

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
async def discover_load_sources(
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

이 함수는 적재를 시작하지 않는다. UI와 CLI가 사용자에게 보여 줄 후보 테이블을 만드는 데만 사용한다.

### 명시 기준월 계획 함수

사용자가 각 원천의 기준월 또는 경로를 명시했을 때만 실제 적재 계획을 만든다.

```python
async def build_full_load_source_set_plan(
    *,
    root_path: Path | None = None,
    juso_yyyymm: str,
    locsum_yyyymm: str,
    navi_yyyymm: str,
    shp_yyyymm: str,
    parcel_link_yyyymm: str | None = None,
    roadaddr_entrance_yyyymm: str | None = None,
    sppn_makarea_yyyymm: str | None = None,
    explicit_paths: dict[str, Path] | None = None,
    allow_mixed_yyyymm: bool = False,
    confirmation_token: str | None = None,
) -> SourceSetPlan: ...
```

규칙:

- `root_path`가 있으면 기준월별 디렉터리/ZIP 이름을 찾아 후보를 고른다.
- `explicit_paths`가 있으면 경로를 우선한다. 이때도 파일명 또는 member명에서 추론 가능한 기준월을 계산하고, 사용자가 입력한 기준월과 다르면 `warning`으로 노출한다.
- 필수 원천은 `juso`, `parcel_link`, `locsum`, `navi`, `shp`다. `roadaddr_entrance`, `sppn_makarea`는 선택 원천이다.
- `allow_mixed_yyyymm=False`인데 기준월이 서로 다르면 계획 생성은 실패한다.
- `allow_mixed_yyyymm=True`인 경우에도 `confirmation_token` 또는 CLI 대화 확인이 있어야 실제 `full_load_batch` 등록으로 넘어간다.
- 계획에는 child job payload가 포함되지만, 이 함수 자체는 큐에 job을 만들지 않는다.

### 큐 등록 함수

계획이 확정된 뒤에만 batch를 등록한다.

```python
async def submit_full_load_source_set(
    plan: SourceSetPlan,
    *,
    requested_by: Literal["cli", "api", "ui"],
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
kraddr-geo load full-set ./data/juso --discover
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

## 테스트 계획

T-045 구현 시 최소 테스트:

- 디렉터리 scan이 `202603`, `202604`, `202605` 후보를 source kind별로 올바르게 매칭한다.
- 같은 기준월 source set은 확인 없이 plan 생성이 가능하다.
- 혼합 기준월 source set은 `allow_mixed_yyyymm=False`에서 실패한다.
- 혼합 기준월 source set은 올바른 confirmation token이 있을 때만 plan 생성이 가능하다.
- CLI 비대화형 실행은 기준월 불일치 시 실패한다.
- CLI 대화형 실행은 확인 문구가 정확할 때만 진행한다.
- REST `discover`와 `plan`은 prompt 없이 구조화된 warning을 반환한다.
- UI reducer는 `idle → uploading → upload_done → source_review → confirming_mismatch → processing → finished` 상태 전이를 보존한다.
- 업로드 중 취소는 partial file을 남기지 않는다.
- 적재 중 취소는 root/child job 상태를 일관되게 `cancelled` 또는 `failed`로 정리한다.

## 후속 구현 범위

- 백엔드 DTO: `SourceCandidate`, `SourceSetDiscovery`, `SourceSetPlan`, `UploadSetStatus`, `UploadFileStatus`
- 라이브러리: `discover_load_sources()`, `build_full_load_source_set_plan()`, `submit_full_load_source_set()`
- CLI: `kraddr-geo load full-set`
- REST: `/v1/admin/load-sources/*`, `/v1/admin/uploads/*`
- UI: `/admin/load` 다중 파일/DND 업로드, 기준월 mismatch modal, 업로드/적재 진행률, 취소 UX
- 정합성: C10의 acknowledged mixed source set 처리
