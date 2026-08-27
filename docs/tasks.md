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
frame-busting 헤더를 보내지 않아 CSP 변경 불필요). 남은 것은 UI 컨테이너 재배포로 라이브 반영하는 단계뿐.

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

### 선행 리뷰 후속

2026-07-27 GitHub 열린 이슈 감사(15건 조사, `tasks-done.md` 참조) 결과 남은 미해결 리뷰 후속 6건
**전부 완료·종료** — 이슈 #298은 PR #491, #302는 PR #493, #299는 PR #495, #252는 PR #497, #307은
PR #499, #201은 PR #502(아래 tasks-done.md 참조). 근거는 각 이슈 본문·코멘트 참조.

### 신규 기능

- [ ] **T-297** — n150 디스크 공간 위험(2026-08-26 T-292 live restore-drill 검증 중
  실제 PostgreSQL 크래시 발생시킴) 사후 조치. 즉시 위험은 2026-08-27 해소(96%→58%,
  189G 여유 — 아래 참조), 남은 항목은 낮은 우선순위 후속.
  - 근본 원인: n150 루트 디스크(`/dev/mapper/ubuntu--vg-ubuntu--lv`, 466G)가 restore-drill
    시작 전부터 이미 98% 사용 중(13G 여유)이었다 — drill의 스크래치 대상 DB
    (`kor_travel_geo_restoretest_20260826T082157Z`, 전국 규모 backup을 `new_database` 모드로
    복원 중, 16GB까지 성장하며 다수의 GIST/btree 인덱스를 빌드하던 도중)가 디스크를 100%까지
    채웠고, PostgreSQL이 WAL을 더 쓸 수 없어 crash했다(unclean shutdown → automatic recovery).
  - 결과: PostgreSQL은 WAL redo로 자체 복구에 성공했다(69초 만에 "database system is ready to
    accept connections"). `kor-travel-geo-api-latest` 컨테이너는 복구 완료 전 접속 실패로
    3회 재시작 루프를 돌다 정상화. 사후 검증: `ops.serving_releases` active release 1건 정상,
    `mv_geocode_target` 6,416,637 row(알려진 정상값과 일치) — **데이터 손실/손상 없음** 확인.
    크래시 원인이 `pg_restore --clean --if-exists` 자체의 결함이 아니라 순수 디스크 용량
    문제임을 확인했으므로(크래시 전 4시간+ 동안 수십 개 테이블/인덱스에 걸쳐 정상 동작 관측),
    T-292는 이 증거 + 로컬 통합 테스트 전체 통과를 근거로 그대로 merge한다(사용자 승인).
  - **즉시 조치 완료 (2026-08-27)**: 남은 16GB 스크래치 restoretest DB DROP(21G 여유,
    96%) → `docker system df`로 실측하니 이 공유 호스트(n150)의 디스크 압박 대부분이
    이 프로젝트가 아니라 **Docker 이미지/빌드 캐시 누적**이었다(다른 프로젝트의 시간별
    스테이징 빌드가 정리 없이 계속 쌓임 — 예: `pinvi-pr477-stage-*` 태그가 서로 다른
    커밋 해시로 40개+ 존재, 각 ~2GB). `docker builder prune -af`(빌드 캐시, 순수
    재생성 가능·무위험) → 61.4GB 회수, 85%(68G 여유). 이어서 사용자 확인 후 `docker image
    prune -af`(어떤 컨테이너도 참조하지 않는 이미지만 삭제, 실행 중 컨테이너는 무영향) →
    추가 회수, **최종 58% 사용(189G 여유)**. 실행 중이거나 정지된 컨테이너가 참조하는
    이미지·볼륨은 전혀 건드리지 않았다(볼륨은 76개 중 32.31GB가 미참조로 잡히지만
    다른 프로젝트 데이터일 수 있어 이번엔 손대지 않음 — 필요해지면 프로젝트별 확인 후
    별도 판단). **위험 수준 해소, 최우선 아님으로 하향.**
  - **남은 후속** (낮은 우선순위): 재발 방지 — `backup_require_free_space_check`가 이
    restore-drill 경로(그리고 일반 `new_database` 복원)에도 적용되는지 확인, 적용 안 된다면
    보강 판단. n150은 다른 프로젝트와 공유하는 호스트라 이미지/빌드 캐시가 다시 쌓일 수
    있으므로, 주기적 `docker system prune` 또는 자동화된 이미지 보존 정책이 있는지(없다면
    kor-travel-docker-manager 쪽에 건의할지) 판단 — 이 저장소 범위 밖일 수 있음.
- [ ] **T-299** — admin UI brand 색(파란 계열, T-298)이 기존 semantic `info` 색과
  hue가 가까워(240 vs 255, 15도 차이) 청색맹(tritanopia) 사용자에게 구분이 어려워질
  위험(T-298 적대적 리뷰 2건이 독립적으로 발견·정량화, PR #540). OKLab 거리 기준
  brand-vs-info 분리도가 teal 때 대비 약 2.6배 감소(0.142→0.055), tritanopia
  시뮬레이션에서도 유사한 감소 확인. 실제 화면 충돌 지점 2곳 확인—
  `components/admin/DagsterPanel.tsx`(backup 스텝 `border-primary/40 bg-primary/5`
  컨테이너 안에 `Badge tone="info"`가 바로 인접), `components/admin/SettingsPanel.tsx`
  (공개 API 키 발급 버튼과 `NoticeAlert variant="info"`가 같은 패널). WCAG "use of
  color" 위반은 아님(텍스트 라벨이 의미를 별도 전달) — T-298 사용자 판단으로 hue=240
  그대로 유지, 드물게 겪는 CVD 유형이라 트레이드오프로 수용했다. 향후 판단 필요:
  brand hue를 info에서 더 멀리(210 부근, 다만 "파란색"보다 "청록"에 가까워 보일 위험)
  옮길지, 아니면 lightness를 낮춰(L 0.47→0.38 부근, tritanopia dE 5.9→15.0로 개선
  확인됨, 대신 버튼이 더 짙은 남색 톤이 됨 — 범위 확대 필요) 색상각은 유지한 채
  분리도를 확보할지, 혹은 `info` 자체의 hue를 재검토할지. 부수 발견: `tailwind.config.ts`의
  하드코딩 `info: "#1d4ed8"`과 `globals.css`의 `--color-info: oklch(0.5 0.14 255)`가
  T-298 이전부터 서로 다른 값이었다(별개 이슈, 이 task 범위 밖).
- [ ] **T-300** — `.nav-link`/`.button`(shadcn 포함)/`.vtable-grid`/`.vtable-scroll`의
  `:focus-visible` 포커스 링이 WCAG 1.4.11(non-text contrast, 최소 3:1) 미달(T-298
  적대적 리뷰에서 발견, PR #540 — T-298이 만든 회귀 아님, teal일 때도 동일하게 미달했음을
  독립 계산으로 확인). 이 요소들은 `:focus-visible`에서 `outline: 2px solid transparent`로
  전역 `outline: 2px solid var(--brand)` 폴백을 무력화하고, 유일한 시각 표시가
  `box-shadow: 0 0 0 Npx color-mix(var(--brand) 24~36%, transparent)` glow뿐인데
  실제 배경(페이지/카드/사이드바/hover 표면)에 alpha-compositing해 보면 1.3:1~1.8:1
  수준(brand hue 변경 전후 차이는 ≤0.03, 무관)으로 3:1 기준에 크게 못 미친다. 별도로,
  `globals.css` 225행(28%, `in srgb`)·529행(18%, `in srgb`)의 이제는 도달 불가능한
  중복 focus-visible 규칙이 2506행·2649행(각 36%/24%, `in oklch`)에 의해 항상 override
  되고 있다(죽은 코드, 청소 대상). `.field input:focus-visible`은 전체 불투명도
  `border-color` 변경도 같이 일어나 문제없음(~6.5:1).

### 선택 후속 (낮은 우선순위)

- **진행 중 작업 없음.** (T-219 잔여 L까지 완료 — `tasks-done.md` 참조.)

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
