# Geo 잔여 작업 감사 — 2026-10-17

## 기준과 판정 범위

- 파일 줄번호는 감사 기준 main cae24c6의 원문 기준이다. 이번 머리말 추가로 바뀐 줄번호와 구분한다.

- GitHub 최신 main: `cae24c6fecc0365433e3937de1d99aa4d9ab543a`(#580). 2026-10-17 조회 시 OPEN PR은 0개다.
- main [CI](https://github.com/digitie/kor-travel-geo/actions/runs/38900864607)와 [OpenAPI drift](https://github.com/digitie/kor-travel-geo/actions/runs/38900864643)는 모두 SUCCESS다. 이번 문서 PR에서는 사용자 지시로 CI를 실행하지 않는다.
- 감사자는 Git/GitHub·공개 문서·운영자가 제공한 비밀 없는 요약만 읽었다. 실제 SSH/Docker/SDK/DB/브라우저·환경파일 접근, 서비스 변경, 새 CPU/메모리 측정은 하지 않았다.
- 소스 완료, 운영 부분 수용, 확인 불가를 분리한다. 공개 요약에서 증거를 못 찾은 것은 **실제 미배포를 뜻하지 않는다**. 이미지 revision label만으로 전체 모듈·wheel·현재 Git와의 동등성을 증명하지 않는다.
- 이 문서의 P1은 다음 수용 순서, P2는 후속 검증, P3는 문서·선택 후속의 우선순위다. 새 운영 장애의 severity 판정이 아니다.

## 완료된 것과 정리할 낡은 기록

| 항목 | 확인한 완료 근거 | 남은 경계 |
| --- | --- | --- |
| Dagster 이관 T-290 | tasks.md:34–54의 Dagster-only 이관·#485 머지 이력 | 예전 “UI 재배포만 남음” 문장을 현재 전체 배포 판정으로 재사용하지 않는다. |
| data_token T-325a~c | [#573](https://github.com/digitie/kor-travel-geo/pull/573), [#574](https://github.com/digitie/kor-travel-geo/pull/574) 머지; tasks.md:73–85의 backfill 기록; 운영자의 읽기 전용 관측에서 유효한 토큰 존재 | 소비자 실제 기준선/변경/재개 수용과 관리 UI 전체 조건은 별도다. 과거 backfill 직후 cache 0행은 사후 복원 불가다. |
| 복원 경로 odroid 이전 | [#575](https://github.com/digitie/kor-travel-geo/pull/575), ADR-070 accepted; tasks.md:90–98의 복원·소비자 전환 기록 | 전국 full-load를 새로 완료했다고 쓰지 않는다. standalone mv_refresh·성능·메모리 잔여는 유지한다. |
| 보조 geometry·요청 수명·조회 부하 | [#576](https://github.com/digitie/kor-travel-geo/pull/576) 머지. 동일 Admin 예제 geometry off/on·좌표·지도 성공 운영 요약 있음 | 취소·부분 실패·재실행 전체 live 및 CPU 원인·전체 SQL timeout 해결 증거는 아니다. |
| Common gRPC/선택 복구/stdlib 채택 소스 | [#577](https://github.com/digitie/kor-travel-geo/pull/577), [#578](https://github.com/digitie/kor-travel-geo/pull/578), [#579](https://github.com/digitie/kor-travel-geo/pull/579) 모두 머지 | 실제 파일/metadata/pyc 정합과 선택 센서 활성화 수용은 아래 G-04/05로 남긴다. 재구현하지 않는다. |
| health 간격·idle CPU·정상 예제 | [#580](https://github.com/digitie/kor-travel-geo/pull/580) 머지. 운영자의 same-image API/CS/UI interval 30/90/30초 적용·건강 확인; idle 전후 90초×3 및 정상 예제 확인 | 새 부하·RSS 수용은 아니다. current main 전체 이미지 재빌드가 필요하다고 단정하지 않는다. |

2026-10-17 **11:58:07 UTC** 운영자 읽기 전용 요약은 전체77/실행16, 실행 중14 healthy·2 healthcheck 미구성·0 unhealthy, daemon OFF를 기록한다. Geo API/UI/CS는 모두 healthy·restart0·OOM false이며 점검 간격은 각각30/30/90초다. 공용 instance YAML SHA256은 `463c83266e36b8b8e79735a36282aac759bc79018eab9c4b4b9302f611432d6e`로 유지됐다. 정지 daemon의 과거 health 문자열을 실행 중 unhealthy 개수에 포함하지 않는다.

같은 요약에서 Geo API/CS revision label은 `ed8b2b1`, UI는 `91c2e499`다. 이들은 최신 main의 ancestor 소스 이력을 가리키지만 라벨만으로 전체 파일 정합·설치 Common·컴파일 결과를 검증한 것이 아니다. 최신 점검 주기는 별도 운영 override 적용으로 확인됐다. 호스트 Geo Git worktree가 관측되지 않았다는 사실도 컨테이너 앱 소스 부재를 뜻하지 않는다.

운영자의 이전 Geo5+Weather3 idle 90초×3 관측은 host 평균 **9.0395%→6.3629%**였다. Geo5 단독90초는 host **5.0306%**였다. 외부 부하가 통제되지 않은 표본이며 인과·수집 작업 성능·현재 전체 서비스 부하로 일반화하지 않는다. NVMe 후 정상 예제는 geometry off167ms/on678ms·HTTP200·좌표/건물도형/지도 settle PASS로 기록됐다. 단발 latency로 reverse p50 회귀나 timeout 실패 경로까지 수용하지 않는다.

## 실제 잔여와 최소 다음 행동

| ID·우선순위 | 현재 상태·작업 | 남은 단계·최소 다음 행동 | 근거 |
| --- | --- | --- | --- |
| G-01 P1 | 운영 수용·조건부 코드 잔여: standalone mv_refresh 1회 실측 후 실행 상한 결정 | 운영 실측·조건부 recovery.py/test 수정·독립 리뷰·CI·머지·배포(코드 변경 시). 운영자가 조용한 창의 standalone wall/메모리/OOM을 기록한다. 현재 21600초와 비교해 ADR070 D4를 결정하고 그 전 schedule/sensor를 켜지 않는다. | `docs/tasks.md:156` / `docs/tasks.md:163` / `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:44` / `kor-travel-geo-dagster/tests/test_definitions.py:86` |
| G-02 P1 | 소비자 통합 수용 잔여: Track1 기준선0·동일0·변경1 및 replay/resume 수용 | 소비자별 통합 테스트·운영 수용 기록. Geo의 기존 token을 쓰는 소비자 소유 격리 수용에서 최초/동일/변경/장애/재개를 검증한다. Geo serving 데이터를 바꿔 시험하지 않는다. 소비자 PR 최신 상태는 해당 담당자가 확인한다. | `docs/adr/069-dataset-data-token.md:240` / `docs/adr/069-dataset-data-token.md:253` / `docs/tasks.md:210` / `track12-n150-map-geo-prereq-ro-root-c18b9ec2-f44f-47d3-be00-77516ca7a256.safe.json` |
| G-03 P1 | 운영 창 재확인 필요: 현재 token·publication 무진행 창과 scheduler OFF 유지 | root fresh 읽기 전용 관측. root가 daemon/schedule 상태, native current runs/load_jobs/publish advisory, token 해시를 수용 전후 재관측한다. 과거 관측을 장기 무변경 증명으로 쓰지 않는다. | `concierge258-geo-window-ro-root-7fc3e657-a7e4-496e-b3ca-d6f4860de665.safe.json` / `docs/tasks.md:98` / `remaining-three-projects-native-read-root-r1-20261017.safe.json` |
| G-04 P2 | 일부 완료·전체 출처 확인 불가: #577–579 실제 artifact/Common/stdlib/health adoption 정산 | 원 build 증거 조회 또는 최소 read-only artifact 대조·문서 정산. 기존 API/CS immutable 이미지의 실제 source/Common 전체 파일·metadata·최종 interpreter checked-hash pyc·유효 HC를 기존 빌드 증거나 좁은 RO probe로 대조한다. cadence 배포만으로 전체 artifact 채택을 선언하거나 무조건 재빌드하지 않는다. | `pyproject.toml:43` / `kor-travel-geo-dagster/pyproject.toml:22` / `docs/runbooks/image-health-bytecode.md:26` / `docs/runbooks/image-health-bytecode.md:45` / `geo580-api-deploy-actual-root-r1-20261017.safe.json` |
| G-05 P2 | 선택 후속·활성화 미확인: native incarnation 복구 센서 origin/물리 소멸 수용 | 실제 origin/namespace/old-worker 소멸 검증·선택적 활성화 결정. 운영 활성화가 필요할 때만 실제 origin·serial 교체·PID/ticks/cgroup 소멸 조건을 검증한다. UNKNOWN 또는 사용자 OFF 지시 중에는 STOPPED를 유지한다. | `docs/common-grpc-health-adoption.md:80` / `docs/common-grpc-health-adoption.md:97` / `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:23` |
| G-06 P2 | 부분 live 완료·전체 수용 잔여: T325 관리 UI data_token 배지·상세·장애 복구 수용 | desktop/mobile live E2E·재현 불가 조건의 mock 대체 기록. 기존 키로 releases/data_token·동일/없음 배지·tooltip·상세 preview·조회 실패/복구를 확인한다. 키 생성/폐기는 읽기 전용 수용에서 제외한다. | `docs/tasks.md:77` / `kor-travel-geo-ui/tests/e2e/live/dataset-version-live.spec.ts:47` / `kor-travel-geo-ui/tests/e2e/live/dataset-version-live.spec.ts:114` |
| G-07 P2 | 정상 예제 완료·오류 수명 수용 잔여: Admin geometry timeout 부분 성공·취소·재실행 live | 안전한 장애 대역 live E2E·관련 문서 정산. 정상 예제·지도는 재개발하지 않는다. 보조 timeout 경고/point 보존, cancel/unmount/stale 응답, 새 요청 복구는 안전한 응답 대역으로 확인하고 실제 SQL timeout 해결로 과장하지 않는다. | `docs/adr/071-optional-geometry-timeout-and-request-lifetime.md:40` / `kor-travel-geo-ui/tests/unit/geocode-resilience.test.tsx:34` / `track-geo-cpu-improvement-nvme-r5-example-20261017.safe.json` |
| G-08 P2 | idle 측정 완료·실부하/RSS 미확인: CPU·메모리 실부하 수용 | standalone mv_refresh/backup cgroup peak·OOM·동일 workload CPU/RSS 비교. 기존 90초×3 idle CPU 결과를 보존한다. Geo CS와 PG를 분리해 실제 작업 wall/peak/RSS/anon/OOM을 기록하며 idle 개선률을 수집/전체 호스트 보장으로 쓰지 않는다. | `geo580-cpu-and-ui-closure-root-r1-20261017.safe.json` / `geo580-geo-only-cpu-90s-root-r1-20261017.safe.json` / `docs/tasks.md:123` / `docs/reviews/2026-10-05-common-dagster.md:48` |
| G-09 P2 | 운영 성능 수용 잔여: reverse p50 회귀<5% 및 n150→odroid p50/p95 | 조용한 창 base/head 교대 또는 소유자 대체 수용 결정. 같은 데이터·키·부하로 표본 N≥200 및 base/head를 대조한다. 열/외부 부하 잡음을 기록하고 단발 Admin ms를 회귀 검증으로 대체하지 않는다. | `docs/tasks.md:80` / `docs/tasks.md:209` |
| G-10 P2 | 운영 상태 확인 불가: n150 중복 API/UI 은퇴와 ensure 재기동 방지 | Manager 기존 depends_on 처리 확인·24h 소비자0·정지 후 읽기 전용 경로 검증. root/Manager 담당자가 실제 n150 중복 상태와 24h peer0, Map ensure 뒤 재기동 부재를 확인한다. 본 감사는 n150 정지나 Manager 작업을 실행하지 않는다. | `docs/tasks.md:203` / `docs/tasks.md:217` |
| G-11 P2 | 미래 재적재 전제·현재 확인 불가: NVMe source/materialized bind와 임시 overlay 제거 조건 | 실제 mount/backing 증거 확인·다음 재적재 전 source/materialized 공유 확인. 기존 NVMe 원천/앱/image를 보존하고 실제 /app/data/source·materialized 공유가 필요 경로에 있는지 확인한다. 조건 미입증 상태에서 overlay를 삭제하거나 full-load를 재실행하지 않는다. | `docs/tasks.md:169` / `docs/tasks.md:220` / `docs/deploy/staging-full-load.md:31` |
| G-12 P3 | 별도 비교 실험 잔여: T063/T326a hardware envelope·반복 benchmark | 3회 SQL/REST/MV/backup-restore 비교·NVMe fio/envelope·빌드 기록 회수. 장비 없음 문구를 현재 상태로 정리하되 자동 부하 시험은 하지 않는다. NVMe에서 승인된 창의 기존 스크립트·동일 snapshot으로 측정한다. | `docs/tasks.md:115` / `docs/tasks.md:244` / `docs/t055-deployment-n150-odroid.md` |
| G-13 P3 | 확정 문서 드리프트: resume/tasks/runbook 최신 완료 근거 반영 | 최소 docs PR·리뷰·머지. #577–580 미머지·cadence 배포대기 문구와 옛 proposed/초기화미완 절은 역사로 구분하고 최신 머리말을 갱신한다. 전체 T325/326 task는 남은 세부 수용 전 체크하지 않는다. | `docs/resume.md:3` / `docs/resume.md:22` / `docs/resume.md:59` / `docs/resume.md:70` / `docs/tasks.md:54` / `docs/deploy/staging-full-load.md:8` / `docs/journal.md:5` |
| G-14 P3 | 소유자 결정 대기·필수 구현 아님: ADR069 phase2 코드 inventory/dataset changes | 착수 여부 결정. 변경 여부 data_token 계약은 이미 구현됐다. 명시 요청 전 코드 단위 diff API를 새로 구현하지 않는다. | `docs/tasks.md:86` / `docs/adr/069-dataset-data-token.md:257` / `docs/adr/069-dataset-data-token.md:445` |

G-02는 Geo가 소비자 계획을 생성하는 새 기능을 뜻하지 않는다. Geo는 data_token API 계약을 제공하며 baseline·계획·replay/resume는 각 소비자 소유다. Geo 선행 PR #573/#574는 머지됐고 Concierge #258 등 소비자 PR의 최신 상태·완료 범위는 해당 저장소 감사가 정본이다. 다른 저장소를 이 감사에서 중복 구현하거나 머지하지 않았다.

## source와 수용의 정확한 경계

- ADR-069 D8: 토큰 없음은 판정 불가, 최초 관측은 기준선 저장만, 동일 토큰은 재계획0, 저장값·새값이 모두 있으며 다를 때만 재해석이다. `version_token` 변경만으로 데이터 변경을 판정하지 않는다. 토큰을 공개 보고서에 원문으로 남기지 않는다.
- Geo 현재 토큰 유효성의 운영 읽기 전용 증거는 있다. 특정 관측에서 active/publish/native runs0·daemon OFF도 기록됐지만 직접 API write 차단은 false였다. 따라서 장기간 publication window 불변을 증명했다고 쓰지 않는다. 수용 전후 fresh 관측과 소비자 자체 재개 검증이 필요하다.
- 현재 `recovery.py:44–50`는 mv_refresh에21600초, LONG_JOBS에는86400초를 준다. 실측 전에 임의로 상한을 늘리거나 tags 인자로만 덮어쓰지 않는다. `geo_job`이 policy tags를 뒤에 병합한다. 기본 RUNNING 정의와 실제 instance의 STOPPED/daemon OFF는 서로 다르므로 소스 기본값을 보고 운영 발화를 허용하지 않는다.
- Common source pin은 Geo API `pyproject.toml:43` 및 Dagster `pyproject.toml:22`의344d91c다. 최신 Common을 무조건 올리는 작업은 이 감사의 결론이 아니다. Manager 공통 변경·미머지 후보 수용은 별도 담당 범위다.
- 공통 UI는 이미 `DagsterPanel.tsx:3–4`, `LoginForm.tsx:3–4`, `AppShell.tsx:28`에서 채택했다. 별도 UI 재구현은 불필요하다. 상세는 명시 선택, 종료 상세 자동 polling 중단, 30초 요약/실패·15초 활성 상세가 source에 있다. 현재 image의 전체 공통 UI 회귀·RSS 감소는 정상 예제 하나로 판정하지 않는다.
- 기존 `dataset-version-live.spec.ts`는 주로 version_token을 비교한다. data_token baseline/변경 수용을 자동으로 대신하지 않는다. 마지막 키 생성/폐기 시험은 명시적 mutation opt-in이므로 읽기 전용 수용에 그대로 포함하지 않는다.

## 낡은 문구와 미확정 항목 처리

`resume.md`의 #573 미머지/proposed, #577–580 준비·리뷰 대기, cadence 배포 대기 등은 작성 시점 기록이다. 최신 판정은 이 문서와 resume/tasks의2026-10-17 머리말을 따른다. journal의 과거 “실제 NOT_RUN”은 삭제하거나 소급 수정하지 않고 새 날짜의 실제 확인 범위를 추가한다.

T-325 관리 UI·reverse p50·cache 즉시0 미검증과 T-326a~c 세부 미완료를 cadence/정상 예제 성공으로 전부 체크하지 않는다. n150 중복 컨테이너 은퇴, 소스/공유 bind·overlay 삭제 조건, 장시간 작업 메모리, 과거 restore wall time은 이번 공개 자료만으로 완료 단정할 수 없다. 기존 데이터 보존과 NVMe 앱/image 유지 원칙을 따른다.

## 권장 실행 순서

1. daemon OFF·Geo 서비스 유지를 그대로 두고 root가 필요한 현재 상태/token·비밀 없는 artifact 정합을 읽기 전용으로 확인한다.
2. 소비자 소유 격리 acceptance와 Geo 관리 UI의 읽기 전용/안전한 장애 대역 수용을 먼저 마친다. 새 Geo serving 릴리스를 발행해 시험하지 않는다.
3. 소유자가 승인한 별도 작업 창에 standalone mv_refresh wall/메모리를 관측해 D4를 결정한다. 코드 변경이 필요할 때만 최소 recovery/test PR→두 독립 리뷰→배포로 잇는다. 본 문서 PR이 schedule 재가동 승인은 아니다.
4. 실제 부하/RSS·reverse 반복 측정·n150 은퇴·다음 full-load mount 전제를 해당 소유자와 정산한다. 끝난 세부 항목만 task 원장에 반영한다.

## 사용한 공개 운영 요약

운영자가 제공한 파일의 비밀 없는 요약만 위 본문에 자체 포함했다. 이 저장소에서 외부 파일을 읽어야만 문서를 이해하는 방식으로 만들지 않는다.

- `remaining-three-projects-native-read-root-r1-20261017.safe.json`: 11:58:07 UTC 현재 상태·주기·labels·YAML; SHA256 `41858f29ba250fc3f112b825bce93e9009944d2b92623dd1845c1444027a35cf`.
- `geo580-{api,cs,ui}-deploy-actual-root-r1-20261017.safe.json`: same-image 주기 변경 및 foreign 보존.
- `geo580-cpu-and-ui-closure-root-r1-20261017.safe.json`: idle 전후90초×3·정상 예제; SHA256 `85d12d4925ccf17944a05b89a43786c84422c716232efae53b36b51d09bba8db`.
- `geo580-geo-only-cpu-90s-root-r1-20261017.safe.json`: Geo5 단독 idle; SHA256 `d1864c4b52583a086a120c60f274ce967deacc41942b40d861811de5ab8a4b35`.
- `track-geo-cpu-improvement-nvme-r5-example-20261017.safe.json`: NVMe 후 정상 예제; SHA256 `6681b9eb736af646d6ca36381e3feba2c333f0be39f662d643fbbc98a5552365`.
- `track12-n150-map-geo-prereq-ro-root-c18b9ec2-f44f-47d3-be00-77516ca7a256.safe.json`: 소비자 경로의 Geo token 존재·형식·읽기 응답.
- `concierge258-geo-window-ro-root-7fc3e657-a7e4-496e-b3ca-d6f4860de665.safe.json`: 특정 시점 active0/token 관측, direct API writes blocked=false.

이 감사의 문서 검증은 diff-check·링크/근거 대조에 한정한다. full suite·이미지 build·새 live UI·새 CPU 계측·운영 변경은0이며 이번 문서 commit은 `[skip ci]`로 생성한다.
