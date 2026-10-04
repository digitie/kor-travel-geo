# 보안 검토 결과: Geo `3f4ddc2..4c59efe` / common `589a01e..73e3ff8`

이번 diff에서 새로 생긴 취약점 가운데 확신도 8 이상으로 보고할 항목은 **없습니다.** 근거는 아래 항목별로 정리했습니다. 이 결론은 코드를 정적으로 읽고 내린 것입니다. 테스트나 runtime·live 검증은 실행하지 않았습니다.

## 검토 범위와 방법
- **검토한 자료:** `geo-security-final-evidence.diff`와 `common-security-final-evidence.diff`를 Read로 읽었습니다.
- **참고한 소스:** Geo는 `F:\dev\kor-travel-geo-codex-dagster-common`, common은 `F:\dev\kor-travel-common-geo-dashboard`의 `packages/ui/src`만 봤습니다.
- **읽지 않은 파일:** 원래의 dirty common, 리뷰어 출력, `.env`, `*.local.md`, 자격증명·live runtime 파일
- **사용한 도구:** Read/Glob/Grep만 썼고 파일은 바꾸지 않았습니다. Task·shell을 쓰지 않았으므로 하위 작업 병렬 분리 대신 같은 흐름 안에서 순서대로 오탐을 걸렀습니다.
- **UI tarball:** Geo의 `vendor/PROVENANCE.md`에는 source `426de4f…`와 SHA256이 적혀 있습니다. tarball 자체를 풀어 hash를 대조하지는 않았습니다. 대신 같은 UI 소스라고 지정된 common 작업 트리를 확인했습니다.

## 검토 항목별 결과

### 1. SSR 로그인 redirect와 common sanitation
대상: `kor-travel-geo-ui/lib/auth.ts:315-327`, `packages/ui/src/navigation.ts:5-16`
- 사용처는 `proxy.ts:25`, `app/login/page.tsx:21`, `app/api/auth/login/route.ts:40`, `lib/session-guard.ts:49` 네 곳입니다.
- 처리 순서는 다음과 같습니다.
  1. `decodeURIComponent`로 한 번 디코딩합니다.
  2. common 함수가 `//`, `\`, 제어문자·공백, 인코딩된 `/`·`\`·제어문자·`%25`를 거부합니다.
  3. `new URL`로 정규화한 뒤 origin이 다르거나 pathname이 `//`로 시작하면 거부합니다.
- 다음 우회 시도는 모두 막히는 것으로 판단했습니다.
  - `/./​/evil`, `/a/..//evil`: 정규화하면 `//evil`이 되어 거부됩니다.
  - `/%2509/…`: 이중 인코딩이라 거부됩니다.
  - `/\t/…`: 제어문자라 거부됩니다.
  - 잘못된 퍼센트 인코딩: 예외가 나서 fallback 경로를 돌려줍니다.
- 이전 구현보다 엄격해졌고, open redirect로 이어질 경로는 찾지 못했습니다.

### 2. 클라이언트 LoginForm
- 서버 응답의 `next`를 `window.location.assign`에 넘기기 전에 common `sanitizeLocalPath`를 다시 적용합니다.
- 로그인 요청에는 25초 timeout이 있습니다.
- form에 `method="post"`가 있어, JS가 동작하지 않아도 자격증명이 URL query로 새지 않습니다.

### 3. AppMenu 내비게이션
- `href`는 정적 `ADMIN_PAGES`에서만 옵니다.
- `DocumentNavLink`에 추가된 `...anchorProps` 전달은 common이 넘기는 `data-slot`, `aria-*` 같은 속성뿐입니다. 사용자가 제어하는 입력은 들어오지 않습니다.

### 4. Dagster 운영 UI (common `dagster-operations.tsx`, Geo `DagsterPanel.tsx`)
- 모든 값은 React 텍스트 노드로 렌더링되고, `dangerouslySetInnerHTML`은 쓰지 않습니다.
- 링크의 기준 URL은 서버 설정값 `dagster_url`이고, run ID와 schedule 이름에는 `encodeURIComponent`를 적용합니다.
- 공격자가 `javascript:` 같은 scheme을 주입할 경로는 없습니다.

### 5. 인증·SSRF·proxy actor scope
- `routers/dagster.py`에서 바뀐 것은 다음뿐입니다. GraphQL URL은 설정값을 그대로 씁니다.
  - query에 `activeRuns`(limit 1000, repository 태그 필터)를 추가
  - 응답을 4 MiB까지만 stream으로 읽도록 제한
  - 전체 timeout(`asyncio.timeout`) 적용
  - 조회용 timeout 설정 분리
- 사용자 입력이 host나 protocol을 정하는 경로는 새로 생기지 않았습니다.
- 라우터 인증 의존성도 바뀌지 않았습니다.

### 6. GraphQL 응답 해석 (`_dagster_client.py:343-355`)
- 응답에 `errors`가 있거나, 알 수 없는 typename·status가 오면 이제 `UNKNOWN`으로 처리합니다.
- 실행 부재를 확정하는 경우를 줄이는 방향이라 보안상 문제가 없습니다.

### 7. 자식 executor 소유권 fence (`load_job_executor.py`, `infra/publication.py`)
- 상태를 바꾸는 쓰기에는 소유권 조건을 붙입니다.
  - 해당 쓰기: heartbeat, progress, done/failed/cancelled, cancel 조회
  - 붙는 조건: `state='running' AND executor='dagster' AND orchestrator_run_id=:owner_run_id`
- 이 조건으로 바뀐 행이 없으면 `LoadJobLeaseLostError`가 나고, 작업은 cancel 신호를 받고 재시도 없이 실패합니다.
- 회수 경로(`reconcile_transition`)는 조회 당시의 run ID와 lease 값을 함께 비교합니다. 그사이 소유권이 바뀌었으면 덮어쓰지 않습니다.
- 게시 guard는 `FOR UPDATE`로 소유 행을 잠근 뒤 같은 transaction 안에서 commit합니다.
- SQL은 모두 bind 파라미터를 씁니다. `_owner_predicate()`로 끼워 넣는 문자열은 상수 SQL 조각이라 SQL injection 경로가 아닙니다.

### 8. 회수기 (`_reconciler.py`)
- 한 번에 100건씩 cursor로 나눠 조회하고, 순회마다 5초 예산을 둡니다.
- Dagster 장애(`UNKNOWN`)일 때는 작업을 유지하거나 아무것도 하지 않습니다.
- 권한 경계를 넘는 쓰기는 없습니다.

### 9. 인프라 재시도 sensor (`kortravelcommon/dagster.py`)
- 재시도는 다음 두 경우에만 허용합니다.
  - 명시적인 인프라 장애 사유
  - `FRAMEWORK_ERROR`이면서 `ChildProcessCrashException`이고 `user_failure_data`가 없는 STEP 실패
- 그 밖의 provider·step 실패가 하나라도 있으면 재시도하지 않습니다.
- checkpoint cursor는 JSON 형식과 타입을 검증하고, `failure_storage_id`가 바뀌면 다시 검증합니다. pickle이나 eval은 쓰지 않습니다.
- Geo에서 재시도를 허용한 작업은 멱등인 `backup_verify` 하나이고, 횟수도 1회입니다.

## 실행하지 않은 검증
- unit 테스트(vitest, pytest)는 실행하지 않았습니다. diff에 들어 있는 다음 테스트 코드는 읽기만 했습니다.
  - Geo: `tests/unit/auth.test.ts`, `test_dagster_*`
  - common: `tests/test_child_crash.py`
- 다음 runtime·live 테스트도 실행하지 않았습니다.
  - `tests/integration/test_dagster_executor_ownership.py`(실제 DB 필요)
  - `tests/crash_fixture.py`(실제 Dagster 자식 프로세스 crash 재현)
  - 실제 Dagster webserver와 PostgreSQL을 쓰는 live 검증
- 따라서 위 결론은 코드 경로를 읽고 내린 판단이며, 실행으로 확인한 결과는 아닙니다.
