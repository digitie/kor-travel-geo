# Geo590 독립 FULL 원문 — exact64ed

판정: **BLOCK (source 수정 필요)**. OPEN P0=0, P1=0, P2=2, P3=1.
기존 retry 입구 oversleep 수정은 확인됐지만 아래 두 신규 경계는 열려 있다.

검토자: James/A. 고정 시각 UTC: 2026-10-18T06:06:18.303845+00:00. 최초 시작 시각은 별도 보존하지 않아 미확인.
Manifest: /home/digitie/dev/geo590-591-p2-review-manifest-c-20261018.json
관찰 SHA256: db59678bc29832ee46e48c274d6191591536abeeadcfb2c562bfafe65d67e3b7
공통 base: 535e26b936978704a3c1ea12b1c15e840321ccdf.

이 검토는 제품 전체 delta와 연결 소스/문서/테스트를 읽은 독립 검토다. 다른 리뷰어의 새 원문/모형을 읽지 않았다. Git show/archive로 exact object를 사용했으며 제품/인덱스/branch를 수정하지 않았다. 현재 root가 원본 WT에서 후속 수정 중인 사실은 관찰했으나 이 보고서 판정에는 포함하지 않는다. 읽은 AGENTS/SKILL/README/agent-workflow/failure-patterns/ADR068 규칙을 적용했다. D4=21600·maintenance 6h·Daemon OFF는 변경되지 않는다.

실제 요청 원문(대화에 보존된 전달 메시지):
> 513freeze받았고B/C 독립리뷰배정했습니다. 이제Geo590/591독립fullreview 진행해주세요. C가590deadline입구체크/591testDSNargv제거 P2수정곧push, 최신freeze먼저C에게확인하여 fixedsnapshot을검토해주세요. WT /home/digitie/dev/kor-travel-geo-codex-lock-takeover-20261018 및 lifecycle-takeover-20261018. base535e26b. reviewerB원문은독립판정전읽지말고 자체source 전체(잠금상한/죽은worker쿼리cleanup)검토, source수정0/운영0. Managerhandoff 경로도보고부탁.
>
> 최종Geo59064ed012f15e20693d1eafa28b4cc70a536041bc7 /59178ea19760e1ecc47df1033e1f80e732791e4e0cc push됨. 해당head로검토해주세요. CHANGELOG P3도최종원문에고정해주시면root단순docsfix후delta확인요청하겠습니다. C현재Managerreview전환.

검증 격리: WSL Ubuntu-26.04, 자기 소유 Git archive 및 임시 fixture. 원 저장소 conftest/env 로딩을 제외하고 plugin autoload를 껐다. 순수 원본 unit 실행에는 네트워크/socket connect·주소 resolve·subprocess·실제 Dagster import를 차단했다. Pytest interpreter /home/digitie/dev/kor-travel-geo-codex-test/.venv/bin/python (Python3.13.14/SQLAlchemy2.0.50)을 읽기 전용으로 사용했다. 추가590 실제함수 AST 반례 로그의 interpreter는 Python3.12.13이다. CodeGraph 대상 CLI 실행은 미확인/NOT_RUN이며 target 전체 graph coverage를 주장하지 않는다.

실제 PostgreSQL, backend/worker signal, Dagster SDK, Docker, SSH, provider, 실데이터/키, 운영, daemon 실행은 NOT_RUN. CI는 제공된 별도 증거이며 본인 실행으로 세지 않았다. source PASS와 운영 수용을 분리한다. SQL timeout/server kernel 동작의 운영값을 추정하지 않는다. 새 CI/full suite/실서비스 조작은 하지 않았다.

## 고정 범위와 검사
Head 64ed012f15e20693d1eafa28b4cc70a536041bc7. base→head 9파일 344+/11-. manifest 파일목록 exact 일치, immutable diff --check exit0.
생산 코드 postload.py, 전체 신규 retry/integration 테스트, CI 및 ADR/상태기록을 읽었다. serving source/SQL/publication guard/기존 cache 경로 연결도 검토했다.
소유 archive /home/digitie/dev/geo590-snapshot-a-6le3s882.
원본 test_region_radius_retry_budget.py + test_postload_mv.py: **14 PASS / 0.99s**.
원본 로그 /home/digitie/dev/geo590-unit-source-a-20261018.public.log.
이 PASS는 아래 새 반례를 포함하지 않는다.

## G590-A-P2-01 — 연결 대기 뒤 만료한 재시도가 LOCK/재생성을 시작한다
위치: src/kortravelgeo/loaders/postload.py:152 및 :156–158.
조건: 첫55P03 뒤 sleep이3599.5초에 끝나 top deadline 검사를 통과하나, engine.begin().__aenter__의 pool/connection 대기가3601초까지 걸린다.
결과: 3600초 예산 뒤에도 LOCK과 전체 SQL 및 publication_guard가 실행되고 commit 성공한다. 예산은 await 전만 검사한다.
재현: 자기 fixture /home/digitie/dev/geo590-review-a-qtrkfm8b/counterexample.py는 exact Git의 class/helper/refresh 함수 AST를 그대로 compile하며 engine/clock/SQL 실행 I/O만 대역한다. 알고리즘 재작성 모형이 아니다.
관찰: raised_original=False, attempts=2, lock_times=[0.0,3601.0], rebuild_times=[3601.0], guards=[3601.0], outcomes=[busy,commit]. 기대 original 오류/no 재생성 assert **FAIL(exit1)**.
원문 로그 /home/digitie/dev/geo590-review-a-qtrkfm8b/counterexample.public.log.
권고: begin 진입 뒤 LOCK 직전 다시 deadline을 확인해 원 busy cause를 보존하고 rollback한다. root가 수용하여 후속 수정 중이라는 전달은 받았지만 이 exacthead에서는 OPEN이다.

## G590-A-P2-02 — acquisition 뒤 기존 유한 lock_timeout을0으로 덮는다
위치: src/kortravelgeo/loaders/postload.py:129–136 (특히136).
조건: 호출 전 session/role/database의 lock_timeout이 예컨대250ms인 지원 구성.
결과: 2초 acquisition 성공 뒤 SET LOCAL lock_timeout=0을 실행하여 이후 rebuild/guard의 기존 유한 lock 정책을 transaction 끝까지 해제한다. “acquisition만2s”라는 범위를 넘어 기존 정책을 완화한다. statement_timeout6h가 있어도 원250ms와 동등하지 않다.
재현: exact helper AST + actual SQLAlchemy text, 관찰 대역 conn prior250ms. 실제 helper 명령은 SET2s→LOCK→SET0, 최종0. prior 유지 assert **FAIL(exit1)**.
파일 /home/digitie/dev/geo590-review-a-qtrkfm8b/timeout_restore_counterexample.py 및 .public.log.
권고: 원 current_setting을 읽어 성공 뒤 transaction-local set_config로 복원. 별도 임의 timeout 기본값을 도입할 필요 없다.
한계: 실제 PG/운영의 prior 값은 측정하지 않았다. 지원 가능한 유한 설정의 소스 계약 회귀이며 현재 운영이250ms라는 주장이 아니다. root 수용/후속 수정 예정이나 exacthead에서는 OPEN이다.

## G590-A-P3-01 — CHANGELOG 누락
AGENTS의 user-visible 변경 기록 요구에 비해 base→head CHANGELOG 변경0. 새 lock/retry 정책을 additive 기록해야 한다. root가 수용한 후속 문서 수정은 별도 closure 대상으로 이 원문에서는 OPEN.

## 나머지 경계/disposition
- 기존 daa5976의 sleep overshoot 후 새 transaction 문제는 last_lock_error+loop 입구 검사로 닫혔다. 원본3회귀를 포함한14개 PASS; await begin 이후 경계는 별도 새 finding이다.
- acquisition55P03만 재시도하고 SQL/guard/기타 DBAPI 오류는 원 예외로 전파한다. 실패 transaction rollback/기존 rows 유지 구조가 보존된다.
- missing first-build table 경로는 기존 의미이며 full rebuild lock hold와 next-table swap은 명시된 별도 잔여다. lock 획득2s를 재생성 전체2s 상한이라고 해석하지 않았다.
- 실제 PG integration과 signal·pool 대기 실측은 NOT_RUN. fake 함수를 통과시킨 결과를 운영 증거로 바꾸지 않았다.
