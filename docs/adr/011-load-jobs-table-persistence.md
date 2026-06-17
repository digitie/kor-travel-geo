# ADR-011: 적재 작업 큐 상태는 `load_jobs` 테이블로 영속화한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
ADR-006은 적재 작업을 `asyncio.Semaphore(1)` 기반 in-process 큐로 직렬 처리하기로 했다. 그러나 분기 풀로드 한 사이클이 30~60분에 달하는 경우 다음 위험이 누적된다.

1. **프로세스 재시작 시 상태 손실**: uvicorn reload, 컨테이너 재기동, 배포 전환으로 `JobQueue._jobs` dict가 휘발. `state=running`이던 작업이 폴링 API에서만 사라지고 DB에는 부분 적재 상태로 남는다.
2. **다중 워커**: `uvicorn --workers N` (N>1) 운영 시 in-process Semaphore가 워커마다 갈라져 동시 실행 위험.
3. **재기동 후 큐잉 잔여**: `state=queued` 작업의 payload 파일(`uploads/*.zip`)이 사라졌는데 큐만 살아 있으면 실행 시 즉시 fail.

ADR-006 결과(부정)의 "매니페스트 기반 재개 필요" open 항목을 본 ADR로 구체화한다.

## 결정
- `load_manifest`는 "성공한 적재의 watermark"로 유지하고, 작업 실행 상태는 **별도 `load_jobs` 테이블**로 분리한다 (`job_id`, `kind`, `payload JSONB`, `state`, `progress`, `current_stage`, `source_checksum`, `error_message`, `started_at`, `finished_at`, `heartbeat_at`, `created_at`).
- `JobQueue`의 상태 전이(`queued → running → done|failed|cancelled`)는 매번 `load_jobs` UPDATE를 동반한다. 진행률/current_stage는 1~5초 throttle로 갱신.
- **lifespan startup 복구**:
  - `state='running'` → 무조건 `failed`로 마크 (재시작으로 끊긴 작업).
  - `state='queued'` → payload(`uploads/*.zip`) 파일이 있으면 재큐잉, 없으면 `failed`.
- **다중 워커 안전성**: 워커가 작업 픽업 직전 `pg_try_advisory_lock(ADVISORY_SLOT_LOAD_QUEUE)` + `FOR UPDATE SKIP LOCKED`로 DB 수준 직렬성 보강. 단일 워커 환경에서도 비용 무시 수준이라 항상 적용.

## 근거
- ADR-006의 in-process 큐는 단일 인스턴스를 가정했지만, 분기 풀로드 60분 동안 reload가 발생할 확률을 0으로 둘 수 없다.
- `load_manifest`(watermark)와 `load_jobs`(실행 큐)를 분리해야 "마지막 성공 적재가 언제인지"와 "지금 실행 중인 작업이 뭔지"의 두 질문이 서로 오염되지 않는다.
- advisory lock + SKIP LOCKED는 PostgreSQL이 제공하는 표준 패턴 — 외부 큐 시스템(Redis/RQ) 도입 없이도 다중 워커 안전성 확보.

## 결과(긍정)
- uvicorn reload/컨테이너 재기동 후에도 작업 상태가 정확히 복구됨.
- `/v1/admin/jobs`가 in-memory 휘발 없이 항상 DB 진실을 반영.
- 다중 워커 운영이 가능해져 ADR-006의 단일 인스턴스 가정을 점진적으로 풀 수 있음.

## 결과(부정)
- `load_jobs` 테이블 추가 마이그레이션(T-006). 진행률 throttle 로직 추가 복잡도.
- payload 영속화로 `uploads/`의 정리 정책(30일 cron)이 `load_jobs.state='done'` 이후로 명확히 묶여야 함.

## 후속
- (open) T-006 DDL에 `load_jobs` 포함. T-015 `_jobs.py` 구현 시 본 ADR의 lifespan recovery + advisory lock 패턴 사용.
- (open) `uvicorn --workers N` 운영 결정은 별도 ADR — 본 ADR은 N>1 가능성을 열어두기만 한다.
