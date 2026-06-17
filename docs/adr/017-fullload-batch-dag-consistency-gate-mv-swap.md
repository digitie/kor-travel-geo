# ADR-017: 전국 풀로드는 batch DAG와 정합성 게이트를 통과한 뒤 MV swap을 수행한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #10 review 반영

## 컨텍스트

ADR-011은 작업 상태를 `load_jobs`에 영속화하고 단일 작업을 직렬 실행하도록 했다. 그러나 분기 단위 전국 풀로드는 단일 파일 적재가 아니라 **여러 정본/보조 데이터셋이 한 묶음으로 성공해야만** 운영 조회면에 노출할 수 있는 작업이다.

예를 들어 `tl_juso_text`만 새 월분으로 갱신되고 `tl_spbd_buld_polygon`이 이전 월분으로 남은 상태에서 `mv_geocode_target`을 swap하면, API는 "새 텍스트 + 옛 도형"의 가짜 정합성 결과를 반환한다. 이 상태는 SQL 오류가 아니라 데이터 운영 오류라서 단순 `state='done'`만으로는 막을 수 없다.

## 결정

전국 풀로드는 `full_load_batch` root job 아래에 child job을 둔 **DAG**로 실행한다.

1. root job: `kind='full_load_batch'`, `load_batch_id = job_id`, 상태는 batch가 끝날 때까지 `running`.
2. 1단계 필수 source load child 5종:
   - `juso_text_load`
   - `juso_parcel_link_load` (T-038에서 추가)
   - `locsum_load`
   - `navi_load`
   - `shp_polygons_load`

   선택 child는 source set에 포함될 때만 등록한다: `pobox_load`(ADR-009 우편번호), `roadaddr_entrance_load`(T-039 direct 출입구 — 기준월이 텍스트 정본과 같을 때만 serving 승격), `bulk_load`. 필수/선택 구분은 `infra/source_set.py`의 `REQUIRED_SOURCE_KINDS`/`OPTIONAL_SOURCE_KINDS`와 일치한다.
3. 1단계 child가 모두 `done`이면 큐가 자동으로 `consistency_check`를 등록한다.
4. `consistency_check`는 `load_consistency_reports.source_set.load_batch_id`에 batch id를 기록한다.
5. 정합성 리포트의 `severity_max`가 `ERROR`이면 batch root를 `failed`로 마크하고 `mv_refresh`를 등록하지 않는다.
6. 정합성 리포트가 `OK`/`INFO`/`WARN`이면 `mv_refresh` child를 `payload.strategy='swap'`으로 자동 등록한다.
7. `mv_refresh`가 끝나면 batch root를 `done`, `progress=1.0`으로 마감한다.

`load_jobs`에는 다음 두 컬럼을 추가한다.

```sql
load_batch_id TEXT,  -- 같은 batch에 속한 root/child를 묶는 id. root는 자기 job_id와 동일.
parent_job_id TEXT   -- root job_id. child가 어떤 batch root 아래인지 추적.
```

## 근거

- 풀로드에서 중요한 것은 개별 파일 적재 성공이 아니라 **동일 기준월 데이터셋 묶음의 원자적 노출**이다.
- 정합성 검증을 batch DAG의 게이트로 두면, 사람이 실수로 `mv_refresh --swap`을 먼저 실행하는 운영 사고를 줄일 수 있다.
- 별도 외부 workflow 엔진을 도입하지 않고도 `load_jobs`와 기존 직렬 큐만으로 재시작 이후 상태 추적이 가능하다.

## 결과(긍정)

- 부분 성공 데이터가 API 조회면에 노출되는 경로가 명확히 차단된다.
- `load_batch_id`로 운영 로그, 진행률, 정합성 리포트, MV swap 이벤트를 한 화면에서 묶어 볼 수 있다.
- `log_tail`/`current_stage`가 root와 child 모두에 남아 장애 분석이 쉬워진다.

## 결과(부정)

- 단순 FIFO 큐보다 상태 전이가 복잡하다. 특히 `consistency_check`가 리포트를 쓰지 않고 성공 처리되는 경우를 별도 실패로 막아야 한다.
- child 구성은 현재 기본 6종으로 고정되어 있다. 우편번호 대량배달처(`bulk_load`)까지 batch 필수 구성으로 넣을지는 운영 데이터셋 확보 후 조정한다.

## 구현 규칙

- source child 중 하나라도 `failed`/`cancelled`가 되면 batch root를 `failed`로 마크하고 아직 `queued`인 같은 batch child는 `cancelled` 처리한다.
- `consistency_check` 성공 후에도 `load_consistency_reports`에 `load_batch_id`가 붙은 최신 리포트가 없으면 `mv_refresh`를 등록하지 않는다.
- `mv_refresh`는 평시에는 concurrent refresh를 쓸 수 있으나, batch DAG가 자동 등록하는 풀로드 후속 작업은 `strategy='swap'`을 사용한다.
