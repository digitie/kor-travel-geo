# Geo591 Popper independent FULL review r1

**REQUEST_CHANGES — OPEN P0=0 / P1=0 / P2=1.**
전체 제품·연결 source를 main535부터 검토했다. CI 시험수정만으로 제품 source PASS를 대신하지 않았다.

## 불변 대상/격리

- repo /home/digitie/dev/kor-travel-geo-codex-lifecycle-takeover-20261018
- effectivebase **535e26b936978704a3c1ea12b1c15e840321ccdf** → exacthead **eded91d67554f25200d50476e0f4094f1d0b2bbd**
- 실제 parent/object를 Git show로 확인. 별도 manifest 파일은 전달되지 않았고 위 fixed source 요청이 기준이다.
- WSL Ubuntu-26.04 / immutable Git object/archive + own ext4 /home/digitie/dev/geo590-591-popper-to4c_bz_/lifecycle. source/index/branch/ref/타인WIP 변경0.
- read-only dependency /tmp/geo591-lifecycle-c-ngozgi70/venv/bin/python: Python3.12.13/SDK1.13.24/SQLA2.1.1. own src와 Dagster src를 editable path보다 앞에 주입했고 원 venv는 변경하지 않았다.
- -I -B/sterile HOME,TMPDIR,PATH/pytest plugins autooff/--noconftest -c /dev/null/no cacheprovider/explicit asyncio plugin. 실제 conftest/env/private local runbook/실데이터를 읽지 않았다. 이번 no-private 지시를 local 필독 요구보다 우선했다.
- AGENTS/README/SKILL·architecture·workflow/failure patterns·변경ADR/task/resume을 확인. author handoff는 scope와 dependency 경로 문맥만이며 모형/결론을 판정으로 합산하지 않았다. 새 peer 원문/모형 미열람.
- 기록확정UTC 2026-10-18T05:54:36.318953+00:00. raw review 요청에 시작UTC는 없으며 임의 복원하지 않는다.

## OPEN G591-B-P2-01 — 선택 integration test의 credential-bearing DSN argv 노출

위치: tests/integration/test_dead_client_statement_cancel.py:104–110, _kill_child_mid_query의 KTG_TEST_PG_DSN positional argument와 _CHILD의 Settings(pg_dsn=sys.argv[1]).

올바른 disposable scratch DB라도 DSN에 password가 있으면 전체 URI가 child argv에 들어가 process metadata/실행 진단 표면에 놓인다. disposable DB명 guard가 credential 노출을 없애 주지 않는다.

exact _CHILD constant와 _kill_child_mid_query actual AST를 compile하고 create_subprocess/READY/wait/signal만 inert process로 대체했다. controlled environ의 공개 synthetic DSN으로 synthetic_dsn_in_child_argv=true/explicit_environment_parameter=false를 확인했다. 실제 process·signal·DB0. 운영 credential을 읽거나 실제 유출됐다고 주장하지 않는다.

DSN은 argv에서 제거하고 이미 상속하는 전용 environ이나 stdin으로 받도록 권고한다. 민감하지 않은 application_name/interval만 argv에 둔다. optional test 범위 P2이며 제품 GUC의 오탐 query cancel로 확대하지 않는다.

## 제품 전체 및 연결 검토

Settings 새정수는 default0/off/ge0. _connect_options는 양수일 때만 ms 옵션을 더하고 기존 statement_timeout/search_path/prepare/pool/metrics를 유지한다. maintenance settings copy가 timeout0+connection check10000을 client resource engine factory에 전달하고 원 Settings/기존 teardown은 보존한다.

제품에 pg_stat_activity를 scan해 다른 PID를 cancel/terminate하는 새 코드가 없다. PostgreSQL의 자기 client socket close polling이다. [PostgreSQL16 공식 설명](https://www.postgresql.org/docs/16/runtime-config-connection.html#GUC-CLIENT-CONNECTION-CHECK-INTERVAL)으로 단위ms/default0/closed socket 의미를 확인했다. 네트워크 장애의 정해진 시간 내 감지는 TCP keepalive 조건도 필요하다. 살아서 멈춘worker·FIN없는network·raw COPY·sync engine·pg_dump/restore 미포함을 docs가 남긴다. 본인이 PG에서 정상 query 오탐0을 검증한 것은 아니다.

ADR/task는 client resource 경로의 좁은 완료이며 모든 direct connection 정리 완료로 확대하지 않았다. D4=21600/statement6h/source geometry/fingerprint·DTO/schema·daemon OFF는 unchanged다.

weakref CI 보강은 구조 등록 smoke만 ephemeral instance 범위로 감싼다. job/op/등록 assertions는 그대로다. 실제 job/SDK pin을 고친 것이 아니고 이 시험 수정으로 sourcefull 판정을 대체하지 않았다. integration은 unique application_name과 실제 pg_sleep active를 확인한 뒤 child를 죽이는 positive/control을 나눈다. 본인 실제 child kill/PG cancel/DB접속은 없다.

## 본인 실행

- exact engine unit + Dagster definitions/source-rebuild25PASS/기존BetaWarning1/2.57s.
- own actual resource/factory2PASS/2.09s: defaultoff, maintenance copy0+10000, 원 Settings동일/검색경로보존, 음수·SQL injection형 문자열 거절, 실제 resource_fn의 engine 인자·client 구성·finally dispose(close=False).
- actual AST inert helper는 위 argv 실패조건을 확인했다. 실제 algorithm을 따로 구현하지 않았다.
- 실제 PG socket close/backend 종료시간/오탐0·실 SIGKILL·production/provider/daemon/CI는 NOT_RUN. 저자150/PG·oldCI 수치를 본인 결과로 합산하지 않는다.


## 불변 source SHA256
- .github/workflows/ci.yml: 9708c50c09b9da5da0f4d7aa62323ba8d55e19c53ee6a2d07561af3aab033196
- docs/adr/068-common-dagster-recovery-and-ui.md: 14c1274f68dde4e4ac26b8af9ac08cfab491932da9e61fc7d7ce331c6f050506
- docs/architecture/backend-package.md: f771f923abf5cdb685255dfad611139f91ecb7fe371e0b89ef120ac7132600fb
- docs/journal.md: cca7ff9f151e38b212e0eecacf9fe363f2b045316d5b07194134b8e4bb391b63
- docs/resume.md: 00fcf71edbca791513eed5f6275b433eeec2fc546a9b309f32a24ee5ae8fcc36
- docs/tasks.md: 90988472ebfbd1381f60fc54f982d6ac61d0ab239223f857507459d78c060975
- kor-travel-geo-dagster/src/kortravelgeo_dagster/resources.py: cc8b5c18df286e643d6d52b3b96e5aaa27c59d02054b88bd8c4efb40dd58b903
- kor-travel-geo-dagster/tests/test_definitions.py: 645c837ffb58cf477d515941f2373910a7325b5ba0adbd97c0ffc27626725db1
- kor-travel-geo-dagster/tests/test_source_rebuild_execute.py: b949c75a67d2fc48c4dc2a2c57b3004f374674070f20f39816a734c6fdf0dff8
- src/kortravelgeo/infra/engine.py: 6a63971a1cd8e337028146c596d71722abc5db39544d050797e9086182404d98
- src/kortravelgeo/settings.py: bf4a8f23132cf322f53acfd368fc59a152fb85a609eb58747eeb071bab7fd57f
- tests/integration/test_dead_client_statement_cancel.py: 3a3288f8fbafdccc486e4c6dcced6189d6a1c1c97fa2dd4e2ed132f61f517c83
- tests/unit/test_infra_engine_pnu_sql.py: c25d8ef46555bdc381c490d4bc21842ff4ff6dda5f1ec7537e0b3af5ace40f80

Git diff-check EXIT0. 운영/SDK worker/실provider/SSH/Docker/RustFS/DB/Daemon/키 접근·새CI·source 수정0. reviewer 한계는 root 기존 위임을 철회하거나 새 승인요건을 만들지 않는다. 보고서 생성 첫 V8 template quote 오류1회는 shell 실행 전이라 파일/제품 변경0이며 정정했다.

## 소유 실행 근거
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lifecycle/test_popper_lifecycle.py: SHA256 ffe1e457dfe79dbbf0d04345dbf451f822dd29c6a498b81aa6df5b74c49b905b
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lifecycle/focused.stdout.txt: SHA256 a121c548d3dd184a68117fae6729951706881ab38c5cf89da799f9cc8a766063
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lifecycle/focused-r2.stdout.txt: SHA256 2cafee716964d9ccf0fea68c4a81d88fa1ccc4879d02c8865b10e93a1d34c281
- /home/digitie/dev/geo590-591-popper-to4c_bz_/lifecycle/argv-credential.safe.json: SHA256 8a58e006dae7af8255ae6ef5a6f7b3083b01184ac555319cb221418342beed7a

## 실제 전달 요청 원문

Common38 리뷰 완료 후 Geo590 daa5976b1a03c582733bc40421747d5a528fbaef, Geo591 eded91d67554f25200d50476e0f4094f1d0b2bbd 독립 적대리뷰 이어주세요. C author. /home/digitie/dev/kor-travel-geo-codex-track-review-20261018 repo/전용WT paths C handoff 예정. #590 잠금상한, #591 죽은worker PG쿼리청소 전체제품에 대해 기존main535 대비 검토+재현·오탐cancel/timeout/rollbacks 중점. CI테스트fix만 보는 것으로 sourcefull판정 대신하지말것. 원문 확정 후 보고. source수정운영0.

후속:

Geo전용WT /home/digitie/dev/kor-travel-geo-codex-lock-takeover-20261018 (#590daa5976) 및 /home/digitie/dev/kor-travel-geo-codex-lifecycle-takeover-20261018 (#591eded91d), effectivebase535e26b936978704a3c1ea12b1c15e840321ccdf. C인계 /home/digitie/dev/geo590-591-takeover-handoff-c-20261018.md. Common38 원문고정 후 이어독립리뷰해주세요.
