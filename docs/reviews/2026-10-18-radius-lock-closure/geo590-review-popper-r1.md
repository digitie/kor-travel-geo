# Geo590 Popper independent FULL review r1

**REQUEST_CHANGES — OPEN P0=0 / P1=0 / P2=1.**
전체 제품·연결 source를 main535부터 검토했다. CI 시험수정만으로 제품 source PASS를 대신하지 않았다.

## 불변 대상/격리

- repo /home/digitie/dev/kor-travel-geo-codex-lock-takeover-20261018
- effectivebase **535e26b936978704a3c1ea12b1c15e840321ccdf** → exacthead **daa5976b1a03c582733bc40421747d5a528fbaef**
- 실제 parent/object를 Git show로 확인. 별도 manifest 파일은 전달되지 않았고 위 fixed source 요청이 기준이다.
- WSL Ubuntu-26.04 / immutable Git object/archive + own ext4 /home/digitie/dev/geo590-591-popper-to4c_bz_/lock. source/index/branch/ref/타인WIP 변경0.
- read-only dependency /tmp/geo591-lifecycle-c-ngozgi70/venv/bin/python: Python3.12.13/SDK1.13.24/SQLA2.1.1. own src와 Dagster src를 editable path보다 앞에 주입했고 원 venv는 변경하지 않았다.
- -I -B/sterile HOME,TMPDIR,PATH/pytest plugins autooff/--noconftest -c /dev/null/no cacheprovider/explicit asyncio plugin. 실제 conftest/env/private local runbook/실데이터를 읽지 않았다. 이번 no-private 지시를 local 필독 요구보다 우선했다.
- AGENTS/README/SKILL·architecture·workflow/failure patterns·변경ADR/task/resume을 확인. author handoff는 scope와 dependency 경로 문맥만이며 모형/결론을 판정으로 합산하지 않았다. 새 peer 원문/모형 미열람.
- 기록확정UTC 2026-10-18T05:54:36.262987+00:00. raw review 요청에 시작UTC는 없으며 임의 복원하지 않는다.

## OPEN G590-B-P2-01 — sleep 후 acquisition deadline 재검사 누락

위치: src/kortravelgeo/loaders/postload.py:147–170, 특히149의 새 시도와162의 sleep 전 검사.

첫 LOCK이55P03으로 실패해 rollback한 뒤30초 sleep이 허용된다. process suspension/event-loop 지연 때문에 실제 재개 시각이3600초 deadline을 넘더라도 새 transaction/LOCK/전체 rebuild/commit을 수행한다. acquisition retry 최대1시간 계약을 지키지 않는다.

actual refresh_region_radius_parts/_lock_region_radius_parts를 import하고 transaction/SQL 대역과 monotonic/sleep clock만 주입했다. 초기0, 첫 lock55P03→clock2, sleep 전2+30<=3600 승인, 실제 sleep을4000초 지연했다. 재개 뒤 두 번째 LOCK/SQL/guard/commit 성공으로 expected DBAPIError가 나오지 않는 RED를 확인했다. retry algorithm을 모형으로 다시 쓰지 않고 실제 함수 await/context-manager를 실행했다.

데이터 손실이나 개별 LOCK2초 상한 파괴 주장은 아니다. 새 재시도 admission의 만료 검사 문제다. rebuild hold까지 무조건1시간으로 제한하라는 권고도 아니다. 첫 시도 이후 retry 직전에 고정 monotonic deadline을 재검사하고 원 lock 예외를 보존해 종료하는 최소수정을 권고한다. root가 후보를 수용해 author에게 배정했지만 이 exact head에서는 OPEN이다.

## 전체 제품 검토

새 ACCESS EXCLUSIVE를 rebuild 전에 명시적으로 얻고 lock_timeout2s로 reader 뒤 대기를 제한한다. LOCK의55P03만 wrapper exception으로 바꿔 engine.begin rollback 뒤 retry한다. 40P01/57014·publication_guard/build의55P03·CancelledError는 재시도하지 않는다.

획득 뒤 lock_timeout0 및 기존 REGION_RADIUS_PARTS_REFRESH_SQL을 같은 transaction에서 실행하고 guard를 commit 전에 호출한다. transaction 구조상 rollback은 있으나 본인이 실제 PG의 row/lock rollback을 실행한 것은 아니다. 첫 table 부재는 명시 lock을 건너뛰고 기존 first-build SQL을 쓴다. 동시 첫 DDL·획득 후 rebuild-until-commit 보유시간 cap은 이 patch 보장이 아니고 source/docs가 next-table swap/a2를 별도 잔여로 남긴다.

refresh_mv concurrent/swap 양 경로가 같은 helper/guard를 호출한다. 원 source/fingerprint/geometry SQL·DTO/API/schema·migration·dependency·D4=21600/statement6h·daemon OFF는 바뀌지 않는다. 1시간 retry와6시간 statement는 run 전체/hold cap이 아니다.

## 본인 실행/원 실패

exact 제품 test_postload_mv11개 + own actual-controlflow6개=17개.
- 첫2FAIL/15PASS/0.79s: 하나는 reviewer --asyncio-mode=auto 누락으로 unmarked async 제품시험을 못 돌린 준비 오류다.
- 명시 auto 정정 뒤1FAIL/16PASS/0.81s, budget negative만 RED.
- pass: busy rollback→새 transaction, guard1회/commit, deadlock40P01·timeout57014 retry0, guard55P03 retry0, CancelledError 전파/context exit.
- 원 제품 assertions는 수정하지 않았다. 실제 PG reader contention/release/PostGIS/worker/operations/CI는 NOT_RUN. integration source3개를 읽었으나 skip를 PASS로 세지 않았다.

root 지적 후 전달 원문:
590P2 받아서C에게반례재현/최소수정배정했습니다. 현재immutable기준 전체리뷰는 끝내고 원문고정해주세요. no source편집. A독립second는수정freeze이후로진행합니다. Manager513 최종freeze도곧나올예정이라 B/C Managerreview 뒤 Geo590delta 가능합니다.


## 불변 source SHA256
- .github/workflows/ci.yml: 291739b9975a36a90a23611970780e0eb2c2695f2d4c74a429a7244375955878
- docs/adr/068-common-dagster-recovery-and-ui.md: 99fde8cb2e5d4ac1fa90c8d545e5074c1eb428d110f7d985a59eca7ddd3a92e0
- docs/journal.md: a3e8001adb9210f663d7a8c3fef2d4c6f473d3a38a63befdaffbc5576f68f9d3
- docs/resume.md: 13ec8063352238133a472df2d68d787288777ccd097f30e2a942e9b0363888cc
- docs/tasks.md: 10628e6598ccfc74f36a739409bc2a414f78f21e07fdc183f98834df45042151
- src/kortravelgeo/loaders/postload.py: 8b1501f9ad0ece0f5860463dfcd288c8312a699cbb7abba96f3c04dcc1092dc1
- tests/integration/test_region_radius_lock_timeout.py: 5afde092049f1bf0ee3dcc4979cee50632bb4836d4dddbf53514b853d51ace23
- tests/unit/test_postload_mv.py: 028bb240503f523236547eea6c877e0c8f94646848e572f1c8bf8e5836e66371

Git diff-check EXIT0. 운영/SDK worker/실provider/SSH/Docker/RustFS/DB/Daemon/키 접근·새CI·source 수정0. reviewer 한계는 root 기존 위임을 철회하거나 새 승인요건을 만들지 않는다. 보고서 생성 첫 V8 template quote 오류1회는 shell 실행 전이라 파일/제품 변경0이며 정정했다.

## 소유 실행 근거
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lock/test_popper_lock.py: SHA256 5f7ed9840ada34da08faa62edf76ec85207a75707dcbee349e4ef09e1a62013a
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lock/focused.stdout.txt: SHA256 14747d4b1e57c8f3d2d4c0f183c497feaee79d83145cee3c81f6861f76e91b0e
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lock/focused-r2.stdout.txt: SHA256 34a76d7bc33221544ae2238e0f22d310a183ee95bb9ce4c2b5078be671f880a6

## 실제 전달 요청 원문

Common38 리뷰 완료 후 Geo590 daa5976b1a03c582733bc40421747d5a528fbaef, Geo591 eded91d67554f25200d50476e0f4094f1d0b2bbd 독립 적대리뷰 이어주세요. C author. /home/digitie/dev/kor-travel-geo-codex-track-review-20261018 repo/전용WT paths C handoff 예정. #590 잠금상한, #591 죽은worker PG쿼리청소 전체제품에 대해 기존main535 대비 검토+재현·오탐cancel/timeout/rollbacks 중점. CI테스트fix만 보는 것으로 sourcefull판정 대신하지말것. 원문 확정 후 보고. source수정운영0.

후속:

Geo전용WT /home/digitie/dev/kor-travel-geo-codex-lock-takeover-20261018 (#590daa5976) 및 /home/digitie/dev/kor-travel-geo-codex-lifecycle-takeover-20261018 (#591eded91d), effectivebase535e26b936978704a3c1ea12b1c15e840321ccdf. C인계 /home/digitie/dev/geo590-591-takeover-handoff-c-20261018.md. Common38 원문고정 후 이어독립리뷰해주세요.
