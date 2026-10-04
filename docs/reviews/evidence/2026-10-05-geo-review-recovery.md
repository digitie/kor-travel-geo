<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 공통 Dagster 적용 독립 적대 리뷰 — Popper 원본

실행 ID: POPPER-GEO-9DB39180-20261005-062833

시작: 2026-10-05T06:28:33.327735+09:00. 검토 종료: 2026-10-05T06:50:34.980758+09:00.

판정: **FAIL**. P1 세 건이 재현되어 열려 있다. 기존 회귀 테스트의 통과는 이 세 경계의 안전성을 입증하지 못한다. 이 원본은 아래 고정 후보만 평가하며 부모의 진행 중 수정이나 다른 리뷰어 결과를 반영하지 않는다.

## 고정 대상과 격리

- 저장소: `F:\dev\kor-travel-geo-codex-dagster-common`.
- base: `3f4ddc2dac3f31634a23ef0e9592f419e29e7d14`.
- 실제 candidate: `9db391807db163ea0eafd09ceb5b434b5870cf47`. Linux Git 객체로 확인했다.
- 공용 UI: `426de4fbad35282bb558712d922c06268e9aba62`. 이전 본인 독립 리뷰 대상이다.
- 공용 Python: `430a9e9cd5429204579792b1d4f8e399366dcb2f`. 재사용 가상환경의 설치 provenance도 이 Git SHA와 일치했다.
- WSL Ubuntu-26.04에서 고정 Git `show`/`diff`/`archive`로 읽었다. 소유 scratch는 `/tmp/popper-geo-9db39180-20261005`이다. 원본 저장소와 부모 mirror의 소스·설치·DB·외부 provider는 변경하지 않았다. 다른 리뷰어 원문이나 통합 판정을 읽지 않았다.
- 재사용 실행 환경: `/home/digitie/dev/kor-travel-geo-codex-dagster-common-test/.venv/bin/python`, Python 3.12.13, Dagster 1.13.24. `PYTHONPATH`는 본인 고정 snapshot의 `src`와 Dagster `src`를 우선했다. PostgreSQL 공격용 DSN은 제거했다.

전체 변경 목록과 실행 정책·등록·복구 상태·reconciler·소유권 SQL·bridge·API/클라이언트·UI adapter·패키징 변경을 검토했다. AGENTS/SKILL 및 관련 운영·ADR 문서를 읽었다. journal을 판정 근거로 사용하지 않았다.

## 직접 수행한 검증

**EXECUTED**:

1. 후보 원래 테스트: `tests/unit/test_dagster_client_recovery.py`, `test_dagster_recovery.py`, `test_dagster_reconciler.py`, `test_dagster_router.py`, Dagster 패키지의 `test_recovery_policy.py`, `test_definitions.py`, `test_backup_maintenance.py`: **103 PASS, 26 warnings, 7.90초**. 로그: scratch의 `focused-original-tests.log`.
2. 원래 `kor-travel-geo-dagster/tests/test_load_job_bridge.py`: **6 PASS, 1.77초**. 직접 실행의 tool stdout으로 확인했다. 원래 테스트 합계 **109 PASS**.
3. 본인 `test_popper_recovery.py`: 실제 asyncio 시간 제한을 쓰는 두 공격 **2 FAIL, 11.18초**. 로그: `popper-recovery-probe.log`. DB/RPC만 주입한 테스트 경계이며 실제 PostgreSQL 실패 주입으로 주장하지 않는다.
4. `native_crash_probe.py`: 실제 multiprocess 하위 프로세스에서 `os._exit(42)`를 실행하고 local SQLite Dagster run/event store의 FAILURE를 관찰했다. 관찰 probe 자체 exit 0.
5. `native_crash_fallback_probe.py`: 동일한 실제 child crash 뒤 공용 factory가 만든 센서의 실제 `evaluate_tick()`을 실행했다. 재시도 요청 1개 기대 assertion **FAIL**. 로그: `native-crash-fallback-probe.log`. 실제 geo 정책 helper와 공용 센서를 사용한 합성 단일 op이며 실제 백업/provider/운영 DB 작업을 호출하지 않았다.
6. Git blob tarball의 SHA256와 lock의 SHA512 integrity를 직접 비교했다. 두 파일 모두 일치했다. 공용 UI operations JS와 모델 선언은 이전 독립 검토한 426de4fb build 결과와 일치했다. tarball LICENSE/NOTICE 포함을 확인했다.

**READONLY**: worker 상태 쓰기의 run/state 조건, reaper의 관찰 run/lease CAS, UNKNOWN/MISSING 해석, active/history keyset 쿼리, SQL timeout, 예약 run-store 오류 보류, job별 retry allowlist, multiprocess 설정, 공용 Python 이벤트 분류, 응답 4 MiB 상한, UI 오류·캐시·DTO 매핑, lock/vendor/Docker/CI 설정.

**NOT_RUN**: 전체 backend 회귀, 실제 PostgreSQL 소유권 7건, 운영 shared Dagster coordinator/monitoring 설정 적용 확인, native retry ON daemon 통합, Dagster 최소 버전 재실행, 실제 provider/백업 복구, frontend 전체 build/browser/live E2E, CI 직접 실행, RSS/최대 동시 run 부하 측정. 부모가 보고한 backend 1782 PASS/101 SKIP, Dagster 150 PASS, frontend 231 PASS 등은 부모 근거이며 본인의 수행 결과로 합산하지 않았다. 진행 중 live/CI는 완료로 세지 않는다.

## B-G-P1-01 — 느린 첫 생존 조회가 뒤의 복구 대상들을 영구적으로 막는다

위치: `src/kortravelgeo/api/_reconciler.py:87-104`, cursor 갱신 `124-127`; 적용 오류의 중단 `115-117`도 같은 head 고정 위험이 있다.

시나리오: 같은 active 페이지의 가장 오래된 run 생존 조회가 매번 tick의 남은 5초를 소모한다. 뒤의 run은 이미 FAILED이고 즉시 확인 가능하다. 첫 조회 timeout은 UNKNOWN으로 안전하게 해석되지만, cursor 갱신 이전의 deadline 검사에서 break한다. 다음 active tick도 동일한 첫 행부터 시작한다. active/history 교대만으로 페이지 내부 진행을 보장할 수 없다.

재현: 첫 행 `slow`의 liveness만 cancellable `asyncio.sleep(3600)`, 둘째 `failed`는 즉시 FAILED를 반환하게 하고 실제 `reconcile_once()`를 active/history/active 세 번 실행했다. 쿼리 주입은 구현의 cursor를 그대로 존중했다. 결과는 `seen=['slow','slow']`, `cursors={False:None,True:None}`, `results=[[],[],[]]`, 적용 횟수 0이었다. 둘째 run이 검사되어야 한다는 assertion이 실패했다. snapshot의 `test_popper_recovery.py:11-28`로 재현 가능하다.

영향: 하나의 오래된 slow/장애 run만으로 이후 running 행이 계속 방치된다. timeout이 있어도 영구 정체가 없어지지 않는다. history의 느린 orphan 처리도 같은 패턴을 검토해야 한다.

권고 및 closure 조건: 행별 생존 조회/적용 예산을 전체 tick보다 작게 제한하고, 안전한 UNKNOWN 평가 이후 다른 행에 진행 기회를 주며 순환 재방문을 유지한다. UNKNOWN을 사망으로 처리해서는 안 된다. slow 첫 행 뒤의 FAILED/MISSING 행이 유한 tick 내에 회수되고, 첫 행도 나중에 재평가되는 회귀를 실제 timeout으로 통과해야 한다.

상태: **OPEN, P1**. 신규 유한 순회 구현의 누락 경계다.

## B-G-P1-02 — 취소 조회의 일시 오류가 감시 task를 죽이고 완료 결과도 실패로 뒤집는다

위치: `kor-travel-geo-dagster/src/kortravelgeo_dagster/load_job_bridge.py:129-133`, cleanup `109-114`, 성공 처리 `106-107`.

시나리오: `read_cancel_requested()`가 한 번 ConnectionError를 내면 `_poll_cancel`이 종료된다. 이후 긴 leaf는 더 이상 취소 권한을 조회하지 않는다. leaf 성공 후 `mark_done()`은 실행되지만 finally의 `await poll`은 CancelledError만 억제하므로 이미 종료된 poll의 ConnectionError가 뒤늦게 호출자에게 전달된다.

재현: executor 테스트 주입 경계에서 첫 취소 조회만 ConnectionError, leaf는 0.01초 후 정상 완료하도록 했다. 결과는 `states=['done']`, `poll_calls=1`, 호출자 오류 `ConnectionError('transient DB read')`였다. 오류가 없어야 한다는 assertion이 실패했다. snapshot의 `test_popper_recovery.py:31-40`으로 재현 가능하다.

영향: 취소 감시가 영구 중단되며 DB done과 native 실패가 어긋날 수 있다. done 행은 현재 reconciler의 running/failed/cancelled 조회에 포함되지 않으므로 이 불일치는 그 복구 경로로 정정되지 않는다. 이것은 base에서 이어진 취소 poll 경계이며 신규 회귀라고 주장하지 않는다. 사용자가 요구한 근본 복구 보강의 잔여 결함이다.

권고 및 closure 조건: 일시 조회 오류를 관찰 가능하게 기록하고 제한된 대기 뒤 재조회한다. poll task의 이미 발생한 일시 오류가 성공한 leaf의 결과를 cleanup 단계에서 대체하지 않도록 한다. 영구 소유권 상실은 즉시 취소에 연결해야 한다. 첫 조회 오류→조회 복원→실제 취소 전파와 첫 조회 오류→leaf 성공→정상 종료 두 경계를 검증해야 한다.

상태: **OPEN, P1**.

## B-G-P1-03 — 신규 multiprocess의 실제 child crash를 인프라 fallback이 제외한다

위치: `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:17-26`, `definitions.py:97-103`; 고정 common430a9e9의 `packages/py/kor-travel-common/src/kortravelcommon/dagster.py:184-190` 및 `199-203`.

시나리오: 멱등 allowlist인 `backup_verify`의 하위 step 프로세스가 예기치 않게 종료되고 native retry는 OFF이다. 새 geo 실행기는 multiprocess이고 인프라 재시도 예산 1을 선언하지만, 공용 센서의 실패 원인 allowlist는 실제 이벤트를 받지 않는다. RUN_EXCEPTION을 허용하더라도 모든 STEP_FAILURE를 거르는 다음 검사도 framework child crash를 제외한다.

실제 이벤트: Dagster 1.13.24의 `os._exit(42)` worker 종료에서 RUN_FAILURE의 `failure_reason=RUN_EXCEPTION`, `error.cls_name=DagsterSubprocessError`, cause/context 없음, `first_step_failure_event=None`이었다. STEP_FAILURE의 `error_source=FRAMEWORK_ERROR`, `error.cls_name=ChildProcessCrashException`, cause/context 없음, `user_failure_data=None`이었다. 일반 provider/op 실패를 주입하지 않았다.

재현: local SQLite DagsterInstance에 `run_retries.enabled=False`, geo `geo_job(name='backup_verify')`와 정상 location tag를 사용했다. 실제 worker 종료 후 공용 `infrastructure_retry_sensor()`의 `evaluate_tick()` 결과는 `requests=0`, `cursor='head'`, 기록된 failure reason RUN_EXCEPTION이었다. 요청 한 개 기대 assertion이 실패했다. scratch의 `native_crash_fallback_probe.py`와 두 native 로그로 재현 가능하다.

영향: 새 실행 방식의 대표적인 child worker 인프라 장애가 자동 복구되지 않는다. head 재순회도 이벤트 분류가 바뀌지 않으므로 복구 요청을 만들지 못한다. retry budget 1 태그가 이 fallback 경로의 복구 가능성을 보장하지 않는다.

권고 및 closure 조건: RUN_EXCEPTION 전체를 무조건 허용하지 말고 framework source 및 ChildProcessCrashException 등 실제 worker crash의 causal evidence로 제한해 허용한다. provider/op STEP_FAILURE, 취소, 원인 불명, 부분 선택, 다른 project/location, 상한 소진은 계속 제외한다. 실제 subprocess crash→fallback 요청, provider 실패→요청 없음, native/fallback 합산 상한 및 호환 버전 회귀를 통과해야 한다.

상태: **OPEN, P1**. geo 신규 multiprocess와 기존 공용 분류의 결합 결함이다.

## 추가 경계와 불확실성

UNKNOWN과 MISSING을 분리하고 관찰 run/lease를 SQL CAS에 함께 넣은 방향은 확인했다. 100행 keyset, 4 MiB GraphQL 응답 제한과 step당 max_concurrent 1은 개별 적재량을 제한한다. 그러나 전역 동시 run 수는 shared coordinator 운영 설정에 의존하며 job 태그만으로 제한되지 않는다. 6시간/24시간 런타임 상한도 실제 shared run monitoring 적용을 이번 리뷰에서 확인하지 않았다.

상태 writer의 5초 lock/60초 statement 제한을 모든 leaf SQL·하위 프로세스의 실행 상한으로 확대 해석하지 않았다. load_jobs 상태 CAS가 모든 leaf 데이터 게시의 fencing까지 입증하지 않는다. 실제 PostgreSQL 경합 및 중지 이후 domain publication은 NOT_RUN이므로 별도 운영/회귀 근거가 필요하다.

vendor UI SHA256는 `03feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43`, tokens는 `554ae3f6a18cbf453130b29f8a2d737ddb880101b55e14535cf8d63174b47505`이며 lock integrity가 맞았다. 원천 라이선스/NOTICE 포함과 이전 공용 UI 후보 코드 일치를 확인했다. 이 정적 확인은 실제 geo UI 동작이나 기존 weather/transport 소비자 회귀를 대신하지 않는다.

P0/P2/P3의 추가 확정 finding은 없다. 위 세 P1은 부모 수정 예정 통보만으로 닫지 않았다. 신규 immutable 후보에서 독립 재현과 별도 post-fix 원본으로 closure를 확인해야 한다.
