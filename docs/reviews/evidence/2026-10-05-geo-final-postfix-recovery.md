<!-- SPDX-License-Identifier: GPL-3.0-only -->

# Geo 공통 복구 최종 후보 독립 post-fix 리뷰 — Popper 원본

실행 ID: POPPER-GEO-C3011220-20261005-070343

시작: 2026-10-05T07:03:43.983791+09:00. 종료: 2026-10-05T07:09:05.639451+09:00.

판정: **FAIL**. 최초 세 P1은 고정 pair에서 CLOSED로 확인했다. 추가 `B-G-P1-04`의 하위 작업 소유권 상실 이후 domain 게시 경계가 재현되어 열려 있다. 부모의 진행 중 수정·live·CI 또는 다른 리뷰어 결과를 이 판정에 섞지 않았다.

## 고정 대상과 격리

- 저장소: `F:\dev\kor-travel-geo-codex-dagster-common`.
- base: `3f4ddc2dac3f31634a23ef0e9592f419e29e7d14`.
- 실제 geo candidate: `c3011220e26e2a733260f429222eeebdcc459680`.
- 실제 공통 Python pin: `92ebfa60ef976d830c08b353de633103650175ad`. 고정 geo `pyproject.toml`과 실행 `PYTHONPATH`를 확인했다.
- 공통 UI: `426de4fbad35282bb558712d922c06268e9aba62`. 최초 후보 이후 vendor 변경 없음.
- Linux Git 고정 객체를 읽고 `/tmp/popper-geo-c3011220-20261005`에 본인 `git archive` snapshot을 만들었다. 최초9db391 검토 맥락과 전체 base→후보 변경, 특히 9db391→c301 delta를 확인했다. journal/통합 판정/상대 raw를 읽지 않았다.
- Python 3.12.13 / Dagster 1.13.24 가상환경은 읽기 전용 재사용했다. fixed common 소스와 fixed geo snapshot만 `PYTHONPATH`로 우선했다. 설치·부모 mirror·원본 소스·운영 DB·provider를 변경하지 않았다. PostgreSQL 공격용 DSN은 제거했다.

## 직접 검증 결과

**EXECUTED**:

1. 후보 원래 테스트의 Dagster client/recovery/reconciler/router, batch DAG, Dagster 정책/등록/backup maintenance/bridge: **123 PASS, 26 warnings, 7.36초**. 로그: scratch의 `focused-original-tests.log`.
2. 최초 본인 실패 공격 두 건을 같은 코드로 재실행: **2 PASS**. 실제 asyncio timeout과 task lifecycle을 사용했다. `independent-attacks.log`의 결과에서 slow 다음 active tick에 failed 행이 조회·수렴됐고, 일시 poll 오류가 leaf 완료 결과를 뒤집지 않았다.
3. 신규 게시 공격 두 건: **2 FAIL, 0.95초**. 첫 공격은 실제 batch orchestration callflow에서 취소 확인 이후 MV/release 호출을 관찰했다. 두 번째는 실제 `postload.refresh_mv()` 및 `shadow_swap_mv()` 소스가 취소 이후 ALTER SQL을 발행하는지 instrumented Engine/Connection으로 확인했다. 로그: `independent-publication-tests.log`. 실제 PostgreSQL의 MV를 변경한 테스트는 아니다.
4. 최초 본인 실제 multiprocess child `os._exit(42)` fixture를 fixed c301 geo + fixed92eb common으로 재실행: **exit 0**, native OFF에서 fallback 요청 **1개**. 로그: `actual-native-crash-postfix.log`. 실제 Dagster local SQLite run/event store를 사용한 합성 op이며 실제 백업/provider는 실행하지 않았다.

**READONLY**: bound child executor와 owner/state predicate, heartbeat LeaseLost 전파, done CAS, adoption, reaper cursor/UNKNOWN/관찰 lease CAS, MV orchestrator 및 실제 swap SQL/active release writer, API 전체 응답 deadline/4 MiB 상한/tick filter, server redirect sanitizer와 UI 연결, 공통 pin.

**NOT_RUN**: 실제 PostgreSQL 소유권/게시 경쟁, 실제 provider·전국 적재/MV 교체·백업, 전체 backend 회귀, frontend 전체 테스트/build/browser/live E2E, CI 직접 실행, shared daemon/coordinator 설정 적용 확인, Dagster 1.9 및 RSS 측정. 부모의 실제 PG8 PASS, backend1786 PASS/102 SKIP, frontend231 PASS 등은 부모 근거이며 독립 수행에 합산하지 않았다. 진행 중 live/CI는 완료로 세지 않는다.

## 최초 finding disposition

- **B-G-P1-01 CLOSED**: `_reconciler.py:100-137`이 시간 상한을 소모한 UNKNOWN 행도 checkpoint한다. 최초 실제 slow-first 공격에서 `seen=['slow','failed']`, 세 tick 내 둘째 행의 CONVERGE_FAILED 및 적용 횟수 1을 확인했다. UNKNOWN 첫 행은 KEEP_RUNNING이며 강제 회수하지 않았다.
- **B-G-P1-02 CLOSED**: `load_job_bridge.py:128-142`의 transient poll 오류를 기록하고 polling을 유지한다. 최초 공격은 `states=['done']`, `error=None`으로 바뀌었다. 후보 원래 새 테스트의 일시 오류→재조회 및 일시 오류→취소 전파도 위 123건 실행에서 통과했다.
- **B-G-P1-03 CLOSED**: common92eb의 strict child-crash 분류를 소비한다. 실제 최초 native OFF worker crash에서 requests 0→1을 확인했다. 공통 자체의 provider/unknown/부분 실행/다음 페이지 혼합 오류/예산 및 native pending 인계 검증은 별도 본인 `common-child-postfix-recovery.md`에 보존했다. 그 원본과 최초 geo FAIL 원본을 수정하지 않았다.

위 최초 severity는 모두 P1로 유지하며, 이 후보에서 수정 closure를 확인한 것이다.

## B-G-P1-04 — child 소유권 상실을 확인한 뒤에도 serving MV와 active release를 게시한다

위치:

- `src/kortravelgeo/loaders/batch_dag.py:859-860`: `_mv_leaf`가 공유 cancel_event를 받지만 버리고 호출한다.
- 같은 파일 `552-592`: `run_mv_refresh`는 첫 progress 이후 링크 갱신→MV refresh→active release 기록을 수행한 뒤에야 다시 progress/소유권을 검사한다. 핵심 게시 호출은 `571-590`이다.
- `src/kortravelgeo/loaders/postload.py:47`의 `refresh_mv`, `102`의 `shadow_swap_mv`: 실제 게시 SQL은 run/lease/cancel을 확인하지 않는다.
- `src/kortravelgeo/infra/admin_repo.py:745-788`: active release 쓰기는 consistency gate를 읽지만 현재 job/run 소유권 predicate가 없다.

시나리오: MV next를 만드는 긴 단계 중 child 행이 취소/회수되거나 다른 run으로 넘어간다. 새 child heartbeat는 LeaseLost를 확인하고 공유 cancel_event를 set한다. 그러나 MV leaf는 이 event를 읽지 않으며 이후 serving swap과 active release 기록을 계속한다. 마지막 progress 또는 mark_done만 owner predicate로 차단돼도 앞선 domain 게시를 되돌리지 못한다.

재현: 본인 `test_popper_publication.py`에서 initial progress는 정상 허용하고 MV build 중 executor를 revoked로 바꿨다. 실제 `_lease_heartbeat`가 LeaseLost를 받아 cancel_event=True가 될 때까지 기다린 후 build를 반환했다. `_drive_child()`와 `run_mv_refresh()`는 실제 고정 소스를 사용했다.

첫 공격 관찰은 `('serving_mv_swapped', True)`, `('release_published', True)`였다. 두 번째 공격은 actual `postload.refresh_mv()`와 actual `shadow_swap_mv()`를 실행하되 Engine/Connection 및 build/cache 보조 작업만 주입했다. 다음 실제 SQL 네 개가 모두 cancel=True 이후 발행됐다.

```text
ALTER MATERIALIZED VIEW mv_geocode_text_search RENAME TO mv_geocode_text_search_old
ALTER MATERIALIZED VIEW mv_geocode_target RENAME TO mv_geocode_target_old
ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target
ALTER MATERIALIZED VIEW mv_geocode_text_search_next RENAME TO mv_geocode_text_search
```

그 뒤 active release 기록 호출도 cancel=True 상태에서 진행됐다. 마지막 progress에서 LeaseLost가 발생했다. 두 공격의 게시가 없어야 한다는 assertion은 실패했다. 실제 PG swap/commit을 실행한 것으로 주장하지 않는다. 소스와 instrumented 호출·SQL 경계로 재현한 결함이다.

영향: 중지/회수된 job의 상태 행은 보호되더라도 serving 데이터와 활성 release가 늦게 바뀔 수 있다. 상태 writer의 fencing과 실제 데이터 게시 fencing은 서로 다른 경계다. 후보의 PG child regression은 leaf 안의 progress가 게시보다 먼저 실행되는 경우만 검사하므로 이 시나리오를 덮지 않는다.

권고 및 closure 조건: cancel/owner 확인을 실제 publication 직전에 연결하고, 확인과 serving swap/active release 저장 사이의 경쟁은 같은 transaction의 owner 조건/잠금 등으로 막는다. 단순 마지막 progress 추가만으로 이미 완료된 게시를 보호할 수 없다. MV build 중 취소/회수→heartbeat 확인→swap/release 없음 및 정상 owner→swap/release 성공을 검증해야 한다. 소유권 확인과 publication 사이에 회수가 들어오는 경쟁도 독립 PostgreSQL schema/fixture로 확인해야 한다.

상태: **OPEN, P1**. base에서 존재하던 domain 게시 경계이며, 이번 bound child executor/heartbeat 보강만으로는 닫히지 않은 근본 중지·복구 계약의 잔여 결함이다. 신규 코드가 처음 만들었다고 주장하지 않는다.

## 다른 확인과 제한

run/state bound writer와 reaper의 observed run/lease CAS는 유지됐다. child가 LeaseLost를 감지하면 공유 cancel_event를 설정하며, status writer가 늦게 terminal을 done으로 덮어쓰는 경계는 차단된다. 다만 이것을 위 domain publication 안전성으로 확대하지 않았다.

API의 trickle chunk 전체 deadline 테스트와 별도 관측 timeout 상한 테스트는 직접 통과했다. 기존 4 MiB 제한과 100행 복구 페이지는 유지된다. 새로운 tick 상태 filter, schedule URL, 메뉴 label 및 서버 sanitizer 변경을 읽었으나 이 리뷰에서 browser 동작을 수행하지 않았다.

전역 run 동시성 및 6시간/24시간 monitoring 상한은 shared instance 운영 설정을 필요로 한다. multiprocess max_concurrent=1만으로 전체 시스템 RSS 상한이나 운영 설정 적용을 입증하지 않는다. 공통 UI/vendor는 변하지 않았다.

P0/P2/P3의 추가 확정 finding은 없다. 새 P1은 부모 수정 계획만으로 닫지 않는다. 새 immutable 후보에서 별도 독립 재현 후 closure를 판단해야 한다.
