# tasks.md — 백로그

열린 `[ ]`(진행 중/대기/보류) task만 두는 백로그. 완료·종료 이력은
[`docs/tasks-done.md`](tasks-done.md), 진척·"다음 한 작업"은 [`docs/resume.md`](resume.md)가
정본이다. 작성·유지 규약(역할 표·라우팅·ID 스킴·entry 형식)은
[`docs/tasks-rule.md`](tasks-rule.md), PR/리뷰 루프·병행 운영 같은 작업 진행 규칙은
[`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다. 현재 상태와 세션 연속성은
[`CLAUDE.md`](../CLAUDE.md)가 정본이다.

작업 항목은 `T-NNN` 형식의 ID로 관리한다(번호 배정은 tasks-rule.md §3). 새 작업은
"대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은
`tasks-done.md` 상단에 누적한다.

## 최신 확인과 남은 수용 (2026-10-17)

[잔여 작업 감사](audits/2026-10-17-remaining-work.md)가 최신 source/운영 부분 수용을 구분한다.
main cae24c6, #573–580은 머지됐고 열린 Geo PR은 없었다. 운영자의11:58:07 UTC 읽기 전용
요약에서 Geo API/UI/CS healthy·restart0/OOM false, 간격30/30/90초, 공용 daemon OFF를 확인했다.
전체77개/실행16개 중14 healthy·2 noHC였으며 instance YAML463c8326을 유지했다.
라벨만으로 전체 모듈·Common/pyc 정합을 검증한 것은 아니다.

- 완료 근거를 반영할 부분: cadence30/90/30 실제 적용, 동일 Admin 주소 예제·지도 정상,
  idle 전후90초×3 표본. 기존 “머지/배포 대기” 문장은 당시 작성 기록으로 읽는다.
- 남은 우선순위: standalone mv_refresh 실측→상한 결정 전 schedule/sensor OFF 유지;
  Track1 소비자 기준선0·동일0·변경/재개 수용; T-325 관리 UI 전체 조건·reverse 성능;
  실제 작업 메모리·n150 중복 은퇴·재적재 mount 전제 확인.
- T-325 잔여 및 T-326a~c 전체 체크는 유지한다. 정상 예제·idle CPU를 전체 수용으로 확대하지 않는다.
  source/리뷰/머지 완료와 artifact/운영 수용 미확정을 구분하며 같은 source를 재구현하지 않는다.

아래2026-10-15 상태·수치와 과거 계획은 이력이다. 완료 세부와 미확정 항목의 최신 구분은 위 감사와
새 운영 증거를 따르며, 이 문서 변경으로 daemon이나 schedule을 시작하지 않는다.

## 현재 세션 상태 (2026-10-15)

열린 항목 인덱스(상세는 아래 섹션; 2026-10-15에 T-324·T-325a~c가 `tasks-done.md`로 갔다).

- [ ] **T-326a~c** — geo 스택 odroid(192.168.1.13) 이전 (ADR-070 **accepted 2026-10-15**, Track 2). **2026-10-14~15 스택 이전은
  풀로드가 아니라 n150 백업 dump 복원(설계 §14-8 지름길 (a), 수동 `pg_restore`)으로 실행됐고 소비자 전환도 끝났다** —
  남은 것은 odroid 실측·standalone `mv_refresh` 실측 → 상한 결정·사후 검증. 아래 "T-326" 섹션.
- [ ] **T-325 잔여 검증** — T-325a~c(#573·#574 머지·odroid 배포) 뒤 실행되지 않은 수용 기준(관리 UI live 확인·reverse
  p50) — 아래 "T-325" 섹션.

## 진행 중

### T-290 — geo 독립 Dagster 오케스트레이션 이관 (epic)

결정 [ADR-066](adr/066-geo-independent-dagster-orchestration.md), 구현 정본
[architecture/dagster-boundary.md](architecture/dagster-boundary.md), 단계·분해·contract·e2e 게이트는
[dagster-migration-plan.md](dagster-migration-plan.md)가 정본. 통합 브랜치
`agent/claude-dagster-migration`(전 milestone 완료 후 main 머지). 두 에이전트 A(실행엔진/백엔드)·
B(배포/관측/e2e) 병렬. **기준: 최소수정 X, 미래지향(유지보수성·안정성·완성도·품질·최적구조).**

- [x] **T-290a** (A) — `kortravelgeo_dagster` 패키지 스캐폴드 + resources + `mv_refresh` @job (M1) — #419
- [x] **T-290b** (A) — Dagster 배포(Dockerfile/compose/메타DB/포트 12502) + n150 mv_refresh run SUCCESS (M1) — #421·#422, manager #47
- [x] **T-290c** (A) — `load_jobs` executor/lease + recovery split + reconciler + cancel 골격 (M1, 4단계 게이트) — #420, 리뷰 후속 #424
- [x] **T-290d** (B) — API GraphQL observe 라우터 (M2) — #417
- [x] **T-290e** (B) — admin `/admin/dagster` 관측 화면 (M2) — #418
- [x] **T-290f** (A) — scheduled backup @schedule 온램프 + @run_failure_sensor + 알림 (M2)
- [x] **T-290g** (A) — `db_backup` Dagster 실행 + verify/copy/restore_drill (M3) — #464 계열
- [x] **T-290h** (B) — run detail 로그·artifact 링크 + 실패/overdue 알림 UI (M3) — #471
- [x] **T-290i** (A) — `db_restore`(새 빈 DB) Dagster 실행, hot-swap 수동 유지, RetryPolicy off (M4) — #472
- [x] **T-290j** (A) — loader + `full_load_batch` Dagster 실행(`batch_dag` 미러 + GDAL 이미지) (M5) — #476/#477
- [x] **T-290k** (A) — in-process 큐/이벤트루프 우회 은퇴, ADR-006/011 superseded (M5) — #479·#480·#481·#482·#483(DDL 0026)
- [x] **T-290l** (B) — live e2e harness를 Dagster 관측까지 확장 + 최종 회귀 (M5) — 전국 full-load 스테이징 라이브 e2e 성공(mv=6,416,637), cutover 배포·검증

**✅ T-290 에픽 완료 (2026-07-12)** — 통합 브랜치 `agent/claude-dagster-migration`(HEAD `9bcb949`)에 병합·n150
cutover 배포·검증 완료. 실행이 프로덕션에서 **Dagster-only**(in-process drain 삭제). live UI e2e 게이트 #1~#4
전부 통과(관측+온램프·backup 실행·restore 새DB·full-load+큐은퇴+최종회귀). 상세는 `tasks-done.md`·`resume.md`.

**후속 완료**: `integration→main` 머지(#485, merge commit `658a54e`) 및 geo Dagster 공개
URL(`geo-dagster.digitie.mywire.org`)을 관리자 `/admin/dagster` 화면에 iframe으로 임베드
(`DagsterEmbed` + `resolveDagsterPublicUrl`, 서버측 `KTG_DAGSTER_PUBLIC_URL` 해석; Dagster UI가
frame-busting 헤더를 보내지 않아 CSP 변경 불필요). 남은 것은 UI 컨테이너 재배포로 라이브 반영하는 단계뿐(2026-07 기록 — 이후 UI 이미지(현재 odroid `91c2e499`)는 #485를
포함하므로 이 단계는 끝났다, 2026-10-17 git 조상 확인).

(그 외 진행 중 작업 없음. T-177A~T-177H·T-183 완료 — `tasks-done.md` 참조.)

## 대기

> 번호 배정 순서·ID 스킴(ADR-050)은 [`docs/tasks-rule.md`](tasks-rule.md) §3을,
> 두 에이전트 병행 권장 순서·병행 운영 원칙(PR/리뷰 루프)은
> [`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다.

T-178a~T-178f Claude Code 리뷰 후속과 T-177 파일 기반 full-load e2e 재검증은 모두 닫혔다.
T-177은 T-073 shell script에 맞추지 않고, opt-in pytest 통합/e2e가 실제 파일을 읽어 scratch
PostgreSQL DB를 구축하는 방향으로 완료했다. 상세 계획과 Task 분해는
[`docs/t177-file-driven-full-load-e2e-plan.md`](t177-file-driven-full-load-e2e-plan.md), 최종
성능 수용은 [`docs/t177h-benchmark-acceptance.md`](t177h-benchmark-acceptance.md)가
정본이다.

### T-325 잔여 — 운영 검증 (T-325a~c 본문은 2026-10-15 `tasks-done.md`)

ADR-069 구현은 머지·배포됐다 — T-325a+b #573(`1c9187d`), T-325c #574(`7d3217c`); odroid DB는 Alembic `0029`, 활성 릴리스
지문 비NULL(`ktgctl serving fingerprint-active` backfill, 2026-10-15 확인). 완료로 옮기면서 **실행되지 않은 수용 기준만** 여기
남긴다 — 운영 검증 면제가 아니다([운영 E2E 미실행 기록](reviews/2026-10-14-odroid-e2e-deferred.md)).

- [ ] **T-325 잔여 검증** — (1) 관리 UI live 확인(데스크톱·모바일, odroid `12505`): releases 표 `data_token` 열·"데이터
  동일"/"지문 없음" 배지·실패 사유 툴팁·상세 대화상자 live preview·재조회 실패/복구. odroid DB는 복원 이력 그대로라 활성
  릴리스(`e0db4ff8…`, 2026-09-28 `manual_rebuild`)만 지문이 있고 이전 릴리스는 전부 지문 NULL — "데이터 동일"·"연속 2회 지문 없음"
  배너는 live에서 재현되지 않을 수 있다(재현 안 되면 mock e2e로 갈음했음을 기록). (2) T-325b 수용 기준 (3) reverse p50 회귀 < 5% —
  2026-10-13 n150 측정은 부하 잡음(±50%)으로 판정 불가였고 스탬프 경로 비용(요청당 ≈2.5 µs)만 측정됐다. odroid도 CPU 열 제약·
  load ≈20이라 같은 문제 — 조용한 창에서 base(`3ee05ee`)/head 교대 측정을 하거나, 소유자가 "경로 비용 측정으로 갈음"을 결정한다.
  (3) T-325a 수용 기준 (4)의 "backfill 직후 `geo_cache` 0행"은 backfill 시각 기록이 없어 사후 확인 불가 — 2026-10-15 08:27Z 2행
  (가장 이른 생성 2026-10-14 21:17Z; backfill은 같은 transaction에서 `clear_on`을 부르므로 그 전이면 정합). 운영자가 backfill
  시각을 journal에 남기거나, 다음 활성화(첫 `mv_refresh`) 직후 0행으로 갈음한다.
- (보류) phase 2 — 코드 단위 인벤토리 + `POST /v2/dataset/changes`(ADR-069 후속). 소유자 결정 뒤 번호 부여.

### T-326 — geo 스택 odroid(192.168.1.13) 이전 + 빈 호스트 풀로드 (ADR-070 accepted 2026-10-15, 이전은 복원 경로로 실행됨, Track 2)

> **2026-10-14~15 실행 상태(운영자 확인 + 2026-10-15 08:2xZ 읽기 전용 재확인, 상세 journal 2026-10-15·ADR-070 "실행 기록").**
> 이전은 아래 계획의 풀로드(8b)가 아니라 **n150 2026-10-12 백업(`kor_travel_geo_backup_20261012T231533Z_zstd3`)을 odroid
> `kor-travel-shared-postgres` 11000에 수동 `pg_restore --jobs=2`**(rc=0, 오류 0, 51표·153인덱스) = 설계 §14-8 지름길 (a)로 했다.
> 그 뒤 Alembic 0028→0029, `ktgctl serving fingerprint-active`(backfill), geo-api(`1c9187d`)·geo-ui(`7d3217c`) odroid 빌드, 공개
> URL `.13` 매핑, geo code-server는 odroid 자체 Dagster plane(2026-10-15 02:52Z, n150 cs는 02:42Z 정지), 소비자 `.13` 호출 확인 —
> Map·PinVi는 키 경로 정상, **concierge는 VWorld 형식 키를 보내 401이었다가 2026-10-15 ≈09:00Z 전용 키 `kor-travel-concierge` 발급 뒤 정상**. **이 경로는 Manager `ensure` 밖에서 호스트 쪽으로 했다.** **소유자 결정(2026-10-15) — ADR-070 accepted**:
> §14-8 = 지름길 (a) 복원으로 갈음(풀로드는 다음 재적재 때), §14-12 = 이전 확정(0.95 GiB 게이트 대신 사후 메모리 관찰), §14-21 = (나)
> 소비자별 키(active `kor-travel-map`·`pinvi-api`·`kor-travel-concierge`), Track 1은 "첫 토큰 = 기준선"(재계획 없음), GeoIP gate는
> 운영 `off` 유지. odroid geo schedule·sensor는 현재 **STOPPED** — standalone `mv_refresh` 실측·상한 결정 뒤 재가동.

결정 [ADR-070](adr/070-odroid-host-and-empty-host-full-load.md)(D1~D9; 소유자 결정 대기 — **accepted 게이트 3건**: 설계
§14-8 소스 ZIP 재확보·serving DB 직접 풀로드·dump 복원 지름길, §14-12 geo 플립 여유 값(0.2 → anon ≤ 0.95 GiB) 또는 n150
잔류, §14-21 키 정책 (가)/(나) — 닫히면 ADR 상태 `accepted`, T-326b PR에서 한 줄; 추천안 수용이면 변경 0인 것: §14-19
Track 1 전량 재계획 수용, §14-4 odroid plane 공개 host, §14-7 geo 백업 off, §14-6 빌드 경로 + Dagster base digest 처리 —
달리 결정되면 amendment). 호스트 쪽 작업(odroid 초기화·PG 인스턴스·Manager `hosts:`·플립 PR·메모리/memswap
정책·소스 bind 상시화)은 **Manager 저장소(ADR-58, T-MGR-01a~05·T-OPS-01~03)가 추적**한다 — 여기서는 geo 몫만.
의존(설계 §11.2 순서 그대로): T-326a(실측)는 지금 가능; T-326b는 Manager odroid 초기화(`prod-deployment.md` §9.1 = 설계
§11.1)·`ensure dagster`(odroid PG)·소스 bind 상시화 머지 **그리고 geo 플립 PR(§11.2 8a) 머지 → n150 geo cs stop → odroid 재설치**
뒤(= 8b; 효과 검사는 런북 순서 0); T-326c는 §11.2 9단계(소비자 URL 전환) 뒤. **분기**: §14-12가 n150 잔류(또는 D6 anon 미달)로
닫히면 ADR 상태 `rejected`(D1·D2만 남김), T-326b/c 닫음. **§14-8 지름길(dump 복원)을 고르면** Dagster `db_restore`는 odroid
NOCREATEDB 롤에서 E0410이라(`infra/db_capabilities.py:3-11`) 수동 `pg_restore`(`shared_admin`) 또는 ADR-58 롤 amendment가 답에
포함돼야 한다(ADR-070 D3-6, 런북 지름길 절). **Track 1 ADR-069(T-325)와 머지 순서 무관**(어느 쪽이 먼저여도 플립은 막히지
않음)이나, T-325 구현 뒤에는 풀로드의 새 `data_token`이 소비자 전량 재계획을 유발한다(ADR-070 D8 — 수용, URL 전환은
`full_load_batch` SUCCESS 다음 날). 런북 [deploy/staging-full-load.md](deploy/staging-full-load.md) "빈 호스트(odroid) 풀로드 — 계획" 절.

- [~] **T-326a** — T-055/T-108 정정 + odroid envelope·n150 anon 실측 (규모 M; T-063 보류 승계)

  **2026-10-15 상태.** 끝난 것: 문서 정정(#572); (3)의 base digest — odroid 빌드 geo code-server 이미지가 `linux/arm64`로
  존재하고 그 안에서 `dagster 1.13.24`·`dagster-postgres 0.29.24`·`sqlalchemy 2.1.1`·`from osgeo import gdal`(3.10.3)이 동작 →
  digest 핀이 arm64로 풀렸다(효과 확인; 그 빌드가 저장소 Dockerfile 그대로였는지는 빌드한 세션 확인 필요 — 바꿨다면 D7 재핀 절차
  대상). ⓒ의 "전환 **전** 기록"은 시점을 놓쳤다 — 대신 전환 **뒤** 값: odroid `ops.public_api_keys` active — 08:27Z 2건(`kor-travel-map`
  2026-08-08, `pinvi-api` 2026-10-14), ≈09:00Z `kor-travel-concierge` 발급으로 3건, `mv_geocode_target`·`tl_juso_text` `count(*)` 둘 다 **6,416,637**(= T-290l 참고값, 복원 원본이
  n150 운영이므로 동일). **ⓐ D6 anon 게이트는 측정 없이 플립됐고 소유자가 사후 관찰로 갈음을 결정(2026-10-15)** — 아래 "남은 것" ⓐ'.
  남은 것: (1) odroid envelope 전부(미실행 — 단 odroid는 무팬 열 제약으로 CPU 1.416 GHz 캡·load ≈20이라 probe 수치에 그 조건을
  병기); ⓐ' odroid 첫 `mv_refresh`·(수동) `db_backup` 중 geo code-server cgroup v1 메모리 최대값·OOM 여부(D6의 사후 판정 — 넘으면
  `mem_limit`/memswap 정책 재검토, Manager §14-14); ⓑ PG anon(Manager 입력, odroid에서); (3) GDAL arm64 빌드 시간·메모리는 빌드한
  세션 기록 회수.

  문서 정정은 이 PR에서 완료 ✅(`docs/t055-deployment-n150-odroid.md` 정정 블록 — x86 가정 → 실측 aarch64 Cortex-A55×4
  1.8 GHz·7,676 MiB·eMMC/NVMe, PG 값은 설계 §5.3(Manager ADR-58 결정 (8)) 포인터; `docs/t108-deploy-automation.md` 보류 블록 — 레지스트리·
  QEMU 불채택, `linux/arm64` 확정). 남은 것: (1) odroid envelope — **지금 가능**(NOPASSWD sudo·docker 그룹 완료, fact base
  §A3): `nvme smart-log`, `docker info`(`Architecture: aarch64`; `No memory limit support`·`No swap limit support` 문자열
  **부재**로 판정 — "WARNING 0건"은 쓰지 않는다), `scripts/capture_deployment_envelope.py --run-probes`(**스크립트 기본
  probe만**: fio randread 8k QD32 ×4 jobs + sysbench cpu/memory, `scripts/capture_deployment_envelope.py:134-176`; 스크립트는
  바꾸지 않는다). 실행 방법: 스크립트는 geo 체크아웃에 있고 odroid 체크아웃은 §11.1-8(Manager 설치)에서야 생기므로 `scp`로
  1파일 반입(의존 `fio`·`sysbench` apt); fio 위치는 `--probe-dir`(`:86-90`; `--fio-size` 기본 1G `:92`)로 eMMC가 아니라
  **지금은** `/mnt/media/<tmp>`(digitie 소유 임시 디렉터리), **디스크 단계(fstab bind) 뒤**에는 `/mnt/media/kor-travel/perf`
  (root:root 트리라 `sudo install -d -o digitie …/perf` 선행); **fstab bind 뒤**(Manager 몫, 미완): **수동 fio 3종**(ADR-070 D9;
  명령줄은 `docs/t055` 정정 블록, 같은 `--directory`)을 Plex 유휴·재생 중 **2회** → `artifacts/perf/n150-vs-odroid-<date>/odroid-m1s/`;
  (2) n150에서 지금 가능한 것 — ⓐ geo code-server `db_backup`·`mv_refresh` 중 cgroup anon 최대값(측정법은 ADR-070 D6;
  run 기동은 다음 야간 schedule을 기다리거나 admin `POST /v1/admin/maintenance/refresh-mv`(`src/kortravelgeo/api/routers/admin.py:1867`
  `@router.post("/maintenance/refresh-mv")` + `app.py:177` prefix — `/v1/admin/loads`에 `kind=mv_refresh`는 source-load op로 가므로
  아님)·`POST /v1/admin/backups`(`routers/admin.py:1928`)로) → **ADR-070 D6 플립 조건 입력**(anon ≤ 0.95 GiB(여유 0.2) — 미달이면
  geo n150 잔류); ⓑ 같은 창의 PG 컨테이너 cgroup anon — D6가 아니라 **Manager 쪽 §14-14(PG `mem_limit 4g` 가드 vs 하드 캡)
  입력**; ⓒ **전환 전 현재 값 기록 1회**(면제 여부는 코드·journal 2026-08-17로 이미 닫힘 — ADR-070 컨텍스트 1): n150 DB
  `SELECT count(*) FROM ops.public_api_keys WHERE state = 'active'`(기대 ≥1) + 명령은 ADR-070 D2(대상 `.14`)로 Map `.env` **키 유효성** 200/401
  + n150 운영 `mv_geocode_target`·`tl_juso_text` `count(*)`(T-326b 6단계 비교 기준) → journal(소유자 §14-21 입력); 가능하면 T-290l
  scratch 풀로드(2026-07-12)의 wall clock을 `load_jobs`/run store에서 회수;
  (3) GDAL arm64 빌드 시간·메모리, Dagster base digest(`kor-travel-geo-dagster/docker/dagster.Dockerfile:34`)의 arm64 manifest
  존재 1회 확인(`docker buildx imagetools inspect` — Dockerfile `:31-32` 주석대로 index digest면 기대 결과이고 재핀 논의 없음;
  amd64 manifest일 때만 T-326b에서 ADR-070 D7 처리).
  - 수정 파일: `artifacts/perf/…`(산출물), `docs/t055-deployment-n150-odroid.md`(실측 수치 기입), `docs/journal.md`.
  - 수용 기준: envelope `system-envelope.md`에 `aarch64`·fio(스크립트 1 + 수동 3) 2회(유휴/재생) 수치; n150 cs anon·PG anon·
    Map 키 상태코드·active 키 수·운영 MV `count(*)`·base digest 확인 결과가 journal에 숫자로 기록돼 D6 판정(옮김/잔류)이 한 줄로
    내려진다.

- [ ] **T-326b** — 빈 호스트 풀로드 실행 + `mv_refresh` run 상한 결정 + `.env.prod.example` 주석 (규모 M, 실행 L)

  **2026-10-18 (G-01, by claude).** 2026-10-15 첫 standalone 시도(`job_fb535a34…`)는 30분 문장 상한(`SET LOCAL '30min'`)에
  걸려 실패했다 — 원인·실측은 journal 2026-10-18. 문장 상한을 `MAINTENANCE_STATEMENT_TIMEOUT='6h'`로(ADR-068 개정, PR
  `agent/claude-g01-locsum-link-join`, #583). **standalone 실측 완료(2026-10-18)**: 소유자 결정으로 code-server 안 `dagster job
  execute`(queue·daemon 밖) — 2156.9 s SUCCESS. D4 (ⅱ) 산식값 3235 s는 **draft PR 보류** — n150 운영 이력(4380~5760 s)과 경합 사례보다
  짧아 소유자 재확인 필요(journal 2026-10-18). CS anon 최대 0.508 GiB·OOM 0,
  PG anon 0.343 GiB(memory.current가 3 GiB 상한에 붙어 reclaim, OOM 0), 최고 73.3 °C. 새 `data_token`은 **바뀌었다** —
  `region_radius_parts`만 달라졌다(아래 후속 d). schedule·sensor는 여전히 끔(재가동은 별도 소유자 결정).
  - [ ] **G-01 후속 d (소유자 결정)** — `region_radius_parts`(매 refresh마다 `ST_Subdivide`로 재생성)의 지문이 플랫폼(n150
    PostGIS 3.5.2/x86 → odroid 3.5.3/arm64)에 따라 달라져 원천 무변경인데 `data_token`이 바뀐다. 지문에서 빼고 원천
    `tl_scco_*`로 갈음할지, 같은 호스트 재실행 결정성부터 확인할지. **이 결정 전에는 Map·concierge 기준선 기록·센서 활성화를
    하지 않는다**(결정적이지 않으면 refresh마다 토큰이 바뀌어 소비자 전량 재계획).
  - [ ] **G-01 daemon ON 전제** — 공용 daemon을 켜면 `dagster/max_runtime`이 집행된다(mv_refresh schedule은 없고 발화는
    admin `refresh-mv`). 켜기 전에 후속 a(region_radius TRUNCATE lock)·b(고아 backend)와 D4 값(재확인)을 닫는다.
  - [x] **G-01 후속 a — lock 대기**(2026-10-18, #590: `LOCK TABLE … ACCESS EXCLUSIVE`를 먼저 `lock_timeout 2s`로, 그 획득만 30 s 간격
    최대 1 h 재시도 — 백업(`pg_dump`의 ACCESS SHARE)과 겹쳐도 reader를 한 번에 2 s 이상 줄 세우지 않고 끝까지 기다린다). **남은 것**:
    획득 뒤 보유(재생성~commit, 6 h 문장 상한) — `_next` 표 재생성 뒤 rename swap으로 줄이는 것은 별도 후속(아래 a2). 원문: `region_radius_parts` TRUNCATE에 `lock_timeout`(예 30s) 또는 `_next` 테이블 swap(문장 상한 6h로
    최악의 AccessExclusive 보유가 30분→6 h, 2차 리뷰 Major).
  - [ ] **G-01 후속 b** — 유지보수 엔진 `client_connection_check_interval`(worker 사망 뒤 고아 backend) + admin cancel이 실행 중
    SQL을 `pg_cancel_backend`로 끊게 할지.
  - [x] **G-01 후속 c** — 데이터 지문 savepoint `10min` → `30min`(소유자 결정 2026-10-18; ADR-069 D5 개정).

  **2026-10-15 상태 — 풀로드는 하지 않았다(복원으로 대체).** 아래 수용 기준의 "지름길 (a)" 분기로 판정하면 적재 몫은 충족:
  수동 `pg_restore` rc=0 + `count(*)` 6,416,637(둘 다, n150 운영 원본과 같음 — 기준월 차이 없음). odroid geo-api env는 D1·D5와
  일치(`KTG_ADMIN_TRUSTED_PROXY_CIDRS` loopback만·`.14` 없음, `KTG_BACKUP_SCHEDULE_ENABLED=false`, `KTG_VWORLD_API_KEY` 비어 있지
  않음, `KTG_DAGSTER_URL`은 공용 plane webserver loopback, `KTG_DAGSTER_PUBLIC_URL`은 `dagster-sub.` host). 복원이 키를 보존해
  Map 키 재발급은 필요 없었다(D2). `.env.prod.example`·`docs/ports.md` 주석은 이 PR에서 정정. **남은 것**: (1) **standalone
  `mv_refresh` 1회 odroid 실측 → D4 상한 결정과 `recovery.py`·`test_definitions.py` 코드**(schedule STOPPED라 아직 한 번도 안
  돌았다; odroid는 열 제약이라 n150 ×3 가정(3.7~4.8 h)보다 길 수 있고 그러면 21600 s 상한에 걸려 cancel된다). **다음 한 걸음(소유자
  지시 2026-10-15)**: 운영자가 schedule 재가동 **전에** odroid에서 standalone `mv_refresh` 1회(`POST /v1/admin/maintenance/refresh-mv`,
  조용한 창)를 돌려 wall clock(초)을 전달 → 그 숫자로 ADR-070 D4 결정((ⅱ) `round(실측 s × 1.5)` 매핑, 실측이 21600 s를 넘으면 (ⅰ)
  `LONG_JOBS`) → `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py`·`tests/test_definitions.py` 기대값 + 일부러 빨갛게 →
  journal에 숫자 → 그 뒤 schedule·sensor 재가동. (2) 복원 소요(wall clock)를 `docs/deploy/staging-full-load.md` 표에(운영자 기록 회수).
  ADR-070 상태 줄은 이 PR에서 accepted로 끝. **풀로드 경로 자체**(소스 반입·`/app/data/source` 상시 bind — odroid geo 컨테이너에 그
  mount가 아직 없다)는 소유자 결정대로 다음 재적재 때의 일이라 이 항목에서 뺀다.

  런북 "빈 호스트(odroid) 풀로드 — 계획" 절대로(순서 0 = §11.2 8a 완료 효과 검사 뒤): 소스 반입(파일 수 > 0·NVMe 장치
  프리플라이트) → `ensure geo` → **serving DB 직접** `full_load_batch`(`target_database` 없음; 라우팅 env 없음 —
  `_full_load_launch.py:9-11`; 이 한 run이 게이트 → `mv_refresh` child까지 돈다, `loaders/batch_dag.py:22`) → **standalone
  `mv_refresh` 1회**(`POST /v1/admin/maintenance/refresh-mv`, D4 입력) → 키 재발급(ADR-070 D2 (나)) → smoke. 소요를 런북 표에
  기록(batch 전체·child·standalone 따로). **`mv_refresh` 상한**(ADR-070 D4, standalone 실측 기준): (ⅰ) `LONG_JOBS`에 추가
  (`kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:15`) 또는 (ⅱ) 실측×1.5를 `policy_for_job`의 job별 초 매핑으로
  (`recovery.py:21-27` → `RecoveryPolicy(max_runtime_seconds=…)`; **job 태그 인자로는 안 된다** — `geo_job`이 policy 태그를 뒤에
  병합해 21600으로 덮는다, `recovery.py:34`; `RecoveryPolicy.tags` 소스는 kortravelcommon이라 구현 전 1회 확인) — 어느 쪽이든
  `kor-travel-geo-dagster/tests/test_definitions.py:76-88`의 `"mv_refresh"` 기대값 동기. **Dagster base digest**(ADR-070 D7):
  T-326a (3)에서 **주석(`dagster.Dockerfile:31-32`)과 달리 amd64 manifest로 확인될 때만** 추천안은 `:34` 두 FROM을 index digest(또는
  arm64 manifest digest)로 재핀 + `tests/test_image_constraints.py:96-102` 기대값 갱신; 설계 §8.2/§8.4의 태그 완화를 소유자가
  고르면 같은 테스트의 완화가 따라온다(§14-6에 병기). ADR 상태 `proposed → accepted` 한 줄(게이트 3건 뒤).
  - 수정 파일: `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py`(필수 — (ⅰ) `LONG_JOBS` 또는 (ⅱ) 매핑),
    `kor-travel-geo-dagster/tests/test_definitions.py`, `kor-travel-geo-dagster/docker/dagster.Dockerfile:34`·
    `kor-travel-geo-dagster/tests/test_image_constraints.py`(digest 재핀 필요 시만), **`.env.prod.example`**(주석만 —
    `KTG_ADMIN_TRUSTED_PROXY_CIDRS` loopback 불변·`.14` 금지(ADR-070 D1), `KTG_DAGSTER_URL`의 `12502`는 standalone 스택 값이라
    "Manager compose 주입" 주석으로, `KTG_DAGSTER_PUBLIC_URL` = odroid plane 공개 host(§14-4), 소스 bind 기본 경로
    `/home/digitie/kor-travel-geo-data/source`와 "EXECUTED_JOB_KINDS 없음" 메모, `KTG_VWORLD_API_KEY` 비면 전부 거부 메모),
    `docs/ports.md:34`(같은 `12502` standalone 서술 정정), `docs/deploy/staging-full-load.md`(소요 표), `docs/adr/070-*.md`
    (상태 줄), `docs/journal.md`·`docs/resume.md`.
  - 수용 기준: 런북 순서 0 효과 검사 PASS(odroid validate의 geo host == odroid); odroid root `.env` `KOR_TRAVEL_GEO_VWORLD_API_KEY`
    비어 있지 않음(발급 전 `/v2/reverse?key=<VWorld 키>` 200 — 비면 `public_api_key.py:66-67`로 전부 거부); 풀로드 run **cancel
    없이 SUCCESS**(consistency report PASS 포함); `mv_refresh` 상한은 **효과로**(ADR-070 D4 — "< 상한의 70 %"는 (ⅱ)에서 항진명제라
    쓰지 않는다): (ⅱ)면 유효 태그 값 == `round(standalone 실측 s × 1.5)`이고 `test_definitions.py` 기대값이 그 숫자, (ⅰ)은 실측이
    21600 s를 넘었을 때만(숫자를 journal에); `mv_geocode_target`·`tl_juso_text` `count(*)` > 0이고 T-326a의 n150 운영 `count(*)`와
    비교해 차이가 기준월로 설명됨(숫자 둘 다 journal — 6,416,637은 참고값); `test_definitions.py` 초록 + **일부러 빨갛게**(기대값 한
    줄 바꿔 실패 확인); 키 재발급 뒤 `/v2/reverse` 200(런북 6단계 curl, 발급 키); 지름길 선택 시 — (a)면 수동 `pg_restore` 종료
    코드 0 + 위 count 기준, (b)면 `POST /v1/admin/restores`가 E0410 없이 run 생성.

- [ ] **T-326c** — 플립 뒤 검증 + Track 1 상호작용 확인 (규모 S, 설계 §11.2 9단계(소비자 URL 전환) 뒤)

  **2026-10-15 구체 점검 목록(소비자 전환은 끝났고 전부 미실행·미기록).** (1) **n150 geo-api 정지 전제가 아직 안 섰다** — n150
  `kor-travel-geo-api-latest`·`-ui-latest`는 Up(code-server만 Exited). 정지는 **Manager T-MGR-01b(n150 compose의 `map → geo`
  `depends_on` 간선 제거) 뒤** — 그 전에는 n150 `ensure map`이 돌 때마다 n150 geo 컨테이너가 되살아난다. 순서: T-MGR-01b 머지·반영 →
  n150 geo-api access log의 24 h 소비자 peer 0을 숫자로 → 정지(Manager) → Map geocode e2e 키 경로 200 → 이후 `ensure map` 1회 뒤에도
  n150 geo가 꺼져 있음을 확인. (2) odroid geo-api access log peer 집계 — 2026-10-15 06:2x~08:2xZ 2 h 동안
  loopback 592건·`192.168.1.14` 1건뿐(로그 형식상 IP만 셌다); Map·PinVi(`pinvi-api` 키)·concierge 각각 키 경로 2xx를 하나씩 상태코드로.
  concierge는 2026-10-15 ≈09:00Z 전용 키 `kor-travel-concierge` 발급 뒤 odroid에서 정상(그 전 VWorld 형식 키로 401) — 상태코드를 journal에. (3) n150 → odroid `/v2/reverse` p50/p95(N ≥ 200, 발급 키) — ADR-070
  D8 ≈2.5 h+ 추정 검증, odroid 열 제약 상태 병기. (4) **Track 1**: 복원이라 `version_token`은 n150과 같은 릴리스(`e0db4ff8…`,
  2026-09-28 `manual_rebuild`)지만 n150 DB는 Alembic 0028이라 `data_token`이 **없었고** odroid에서 처음 생겼다(NULL → `dd1-…`).
  소유자 결정(2026-10-15): 첫 토큰은 **기준선**(저장만, 재계획 없음 — ADR-069 D8 amendment, 소비자 구현은 Map ADR-109·concierge) →
  Map·concierge 센서의 실제 계획 건수 **0**과 저장된 기준선 토큰을 journal에(0이 아니면 소비자 구현 결함으로 해당 저장소에 전달). (5) odroid Dagster: geo schedule·sensor
  STOPPED → 재가동 결정(위 T-326b (1) 상한 결정 뒤); 08:26Z 공용 plane `daemon`·`webserver`가 `unhealthy`, geo-ui도 healthcheck
  5 s timeout으로 `unhealthy`(UI는 응답) — Manager 쪽 확인. (6) overlay 삭제 조건은 아래 그대로.

  n150 geo-api **stop 상태**에서 Map geocode e2e 키 경로 200 + odroid access log peer `192.168.1.14`; n150→odroid
  `/v2/reverse` p50/p95(ADR-070 D8 ≈2.5 h+ 추정 검증); Track 1 센서는 **조건부** — T-325(ADR-069) 구현 완료 상태면 URL 전환 뒤
  계획 1건 생성(재계획 수용; dump 복원이면 0건) 확인, 미구현이면 이 항목 해당 없음(journal에 어느 쪽인지 기록);
  `docs/deploy/docker-compose.geo-source-vol.yml` 삭제는 Manager 상시 bind 머지 **그리고** `geo-materialize` 공유 볼륨이 Manager
  compose에 들어가거나 `source_rebuild_db` 경로 불사용 결정 뒤(overlay `:31,34,37` — ADR-070 D3-2).
  - 수정 파일: `docs/deploy/docker-compose.geo-source-vol.yml`(조건 충족 시 삭제), `docs/deploy/staging-full-load.md`,
    `docs/journal.md`·`docs/resume.md`.
  - 수용 기준: 위 효과 전부 숫자·로그로 journal에; "200이면 통과"만으로 닫지 않는다.

### T-308 공용 instance 이전 후속 (2026-09-28 사고 조사에서 나온 것)

근거와 증거는 `docs/journal.md` 2026-09-28·2026-09-29 항목. T-309~T-318은 2026-09-29에 완료
(`tasks-done.md`). 아래는 그 리뷰에서 나온 후속이다. 우선순위 순.


### 선행 리뷰 후속

2026-07-27 GitHub 열린 이슈 감사(15건 조사, `tasks-done.md` 참조) 결과 남은 미해결 리뷰 후속 6건
**전부 완료·종료** — 이슈 #298은 PR #491, #302는 PR #493, #299는 PR #495, #252는 PR #497, #307은
PR #499, #201은 PR #502(아래 tasks-done.md 참조). 근거는 각 이슈 본문·코멘트 참조.

### 선택 후속 (낮은 우선순위)

- **진행 중 작업 없음.** (T-219 잔여 L까지 완료 — `tasks-done.md` 참조.)

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
  **2026-10-13**: odroid(ODROID M1S, 실측)가 있으므로 odroid 몫은 **T-326a**가 승계한다(`docs/t055` 정정 블록) —
  이 항목은 SQL/REST 벤치마크 3회 반복 등 T-326a 범위 밖의 비교 측정만 남긴다.
