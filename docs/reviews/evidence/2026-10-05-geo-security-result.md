# 보안 리뷰 결과: Geo `3f4ddc2d..596b7d17` · common `589a01ef..ab21cc3b`

## 결론

신뢰도 8 이상으로 실제 악용 가능한 취약점은 **없습니다**. HIGH와 MEDIUM 모두 0건입니다.

## 검토 범위와 방법

- **읽은 자료:** 고정 diff 2개(`geo-security-merge.diff`, `common-security-merge.diff`), Geo 소스 `F:\dev\kor-travel-geo-codex-dagster-common`, common 소스 `F:\dev\kor-travel-common-geo-dashboard`.
- **사용 도구:** Read/Glob/Grep만 썼습니다. shell, Task, 파일 변경은 하지 않았습니다.
- **읽지 않은 것:** 원본 dirty common, 이전 리뷰어 산출물, `.env`, `*.local.md`, 자격증명, live 런타임 파일.
- **진행 방식:** 취약점 후보를 찾은 뒤 오탐 필터링 기준을 순서대로 적용했습니다.

## 영역별 검토 내용 (모두 오탐이거나 보고 기준 미달)

1. **SSR 로그인 리다이렉트와 common 경로 정리**
   - 대상: `kor-travel-geo-ui/lib/auth.ts:315-327`, common `packages/ui/src/navigation.ts:5-16`.
   - Geo는 한 번 디코딩한 뒤 common 정리 함수에 넘깁니다. common은 다음을 모두 거부합니다.
     - `//`로 시작하는 경로, `\`, 제어문자와 공백
     - `%2f`, `%5c`, `%0x`, `%1x`, `%20`, `%7f`, `%25` 같은 인코딩된 경계 문자
     - `new URL` 정규화 후 origin이 바뀌거나 경로가 `//`로 시작하는 경우
   - 그래서 `/.//evil`, `/%252F%252Fevil`, `/%09/evil` 같은 우회 시도는 모두 fallback 경로로 막힙니다.
   - 같은 함수를 쓰는 곳: `proxy.ts:25`, `app/api/auth/login/route.ts:40`, `lib/session-guard.ts:49`, `app/login/page.tsx:21`.
   - 클라이언트 `LoginForm.tsx:22`도 서버 응답의 `next`를 다시 정리한 뒤 `location.assign`에 넘깁니다. open redirect는 없습니다.

2. **AppMenu와 DocumentNavLink 탐색**
   - `AppShell.tsx`의 메뉴 `href`는 정적 상수(`ADMIN_PAGES`, `ADMIN_NAV_GROUPS`)입니다.
   - `DocumentNavLink`에 새로 전달되는 `anchorProps`는 common `AppMenu`가 만든 값뿐이라 외부 입력이 들어갈 경로가 없습니다.

3. **XSS 가능성 (DagsterOperations / DagsterPanel)**
   - 실패 메시지, tick 오류, 스케줄 이름, 시간대는 모두 React 텍스트 노드로 출력됩니다. `dangerouslySetInnerHTML`은 쓰지 않습니다.
   - 링크 URL은 서버 설정 값인 `dagster_url`과 `encodeURIComponent`로 인코딩한 이름으로만 만들어집니다.

4. **GraphQL 범위 제한과 응답 상한**
   - 새로 추가된 `activeRuns`도 기존 `runsOrError`와 같은 `.dagster/repository = $repositoryLabel` 태그로 범위가 제한됩니다(`routers/dagster.py:146-170`). 다른 location의 실행이 노출되지 않습니다.
   - `_post_graphql`의 4 MiB 상한과 전체 응답 시간 제한은 강화 조치입니다. DoS 계열이라 보고 대상에서도 제외됩니다.

5. **SSRF와 proxy 접근 범위**
   - 이번 diff는 Dagster GraphQL 호출 대상 host나 protocol을 사용자 입력에서 받지 않습니다. `graphql_url`은 settings 값입니다.
   - `proxy.ts`의 actor 범위 로직은 이번 diff에서 바뀌지 않았습니다.

6. **SQL 구성 방식**
   - `load_job_executor.py`에서 f-string으로 붙이는 `_owner_predicate()`는 고정 문자열입니다. 실제 값은 모두 bind parameter로 들어갑니다.
   - `_reconciler.py`의 keyset 조회와 `publication.py`의 `FOR UPDATE` 확인도 모두 parameter 바인딩을 씁니다. injection 경로는 없습니다.

7. **자식 executor 소유권 확인과 취소·회수 경계**
   - `renew_lease`, `set_progress`, `mark_done`은 `state='running'`, `executor='dagster'`, `orchestrator_run_id` 일치를 조건으로 갱신합니다.
   - `reconcile_transition`은 관측한 run ID와 lease 값이 그대로일 때만(CAS) 상태를 바꿉니다.
   - `UNKNOWN` 상태에서는 회수를 보류합니다. 늦게 끝난 worker가 이미 끝난 상태를 덮어쓸 수 없는 방향의 변경입니다.
   - 남은 경계 사례는 정합성·가용성 문제일 뿐 권한 상승이나 데이터 노출로 이어지지 않습니다.

8. **인프라 재시도, provider 거부, 예산**
   - common `dagster.py:221-290`의 재시도 조건은 다음을 모두 만족해야 합니다.
     - `RUN_EXCEPTION`이면서 오류 종류가 `DagsterSubprocessError`
     - 모든 step 실패가 `FRAMEWORK_ERROR` + `ChildProcessCrashException`이고 user failure가 없음
   - Geo에서는 읽기 전용 `backup_verify`에만 1회 허용합니다. 복원·적재 같은 비멱등 작업은 0회입니다.
   - sensor cursor의 checkpoint JSON은 Dagster 내부 상태이고 형식을 엄격히 검증하므로 신뢰 경계를 넘는 입력이 아닙니다.
   - 시간 예산 관련 사항은 DoS/자원 계열이라 제외했습니다.

9. **CI 설정**
   - `ci.yml`의 `postgres:postgres` DSN은 CI service container용 테스트 자격증명이라 보고 대상에서 제외했습니다.

## 실행하지 않은 검증

이번 판정은 코드를 읽고 내린 정적 분석입니다. 아래 항목은 이 리뷰에서 실행하지 않았습니다. diff 문서에 PASS로 적힌 결과도 직접 다시 확인하지 않았습니다.

- **단위·통합 테스트**
  - Geo backend pytest(`test_dagster_executor_ownership.py` 등)
  - common `test_child_crash.py`와 `crash_fixture.py`의 실제 `os._exit(42)` 자식 프로세스 종료 재현
  - frontend vitest
- **live 검증**
  - n150 live UI E2E
  - 실제 Dagster instance에서 sensor tick 동작
  - 배포 환경에서 로그인 리다이렉트 확인
- **산출물 확인**
  - vendor tarball의 SHA256과 lock integrity 대조
