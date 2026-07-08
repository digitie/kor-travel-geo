# Dagster 이관 마스터플랜 (T-290)

geo 백업/복원·적재 오케스트레이션을 서비스 전용 독립 Dagster로 이관하는 **위상(phased) 실행 계획**.
결정은 [ADR-066](adr/066-geo-independent-dagster-orchestration.md), 구현 정본은
[architecture/dagster-boundary.md](architecture/dagster-boundary.md), 수렴 리뷰는
[backup-restore-orchestration.md](backup-restore-orchestration.md). 작업 ID는 tasks.md에 등재된 **T-290**
epic + 하위 task다.

원칙(사용자 지시): **최소수정이 아니라 미래지향 — 유지보수성·안정성·완성도·코드품질·최적구조 중심.**
leaf(도메인) 로직은 재사용하되 오케스트레이션은 map 청사진 수준으로 완성도 있게 이식한다.

## 0. 병렬 운영 모델 (두 에이전트 A·B)

- **통합 브랜치** `agent/claude-dagster-migration`(main 청정 유지). 모든 task PR은 **이 통합 브랜치를
  base로** 머지하고, **전 milestone 완료 후 통합 브랜치를 main에 머지**한다.
- 각 task는 하위 branch → PR(base=통합) → CI green → 머지. PR 단위로 리뷰 가능하게 작게 쪼갠다.
- **Agent A = "Dagster 실행 엔진 + 백엔드"**: `kortravelgeo_dagster` 패키지, `load_jobs` executor/recovery,
  backup/restore/loader/full-load op, 파괴적 op 규칙.
- **Agent B = "배포 인프라 + 관측 표면(API/UI) + e2e"**: Dagster 배포(compose/Dockerfile/DB/port), API
  GraphQL observe 라우터, admin `/admin/dagster` 임베드, 실패/overdue 알림 UI, live e2e harness·spec.
- A·B는 **주로 서로 다른 파일 영역**을 만져 충돌이 적다. 결합점은 §1의 **contract**로 먼저 고정한다.

## 1. 병렬을 위한 contract (M1 착수 전 확정 — A·B가 이걸 기준으로 각자 개발)

| contract | 값(확정) |
|---|---|
| distribution / import root | `kortravelgeo-dagster` / `kortravelgeo_dagster` |
| code location module | `kortravelgeo_dagster.definitions` |
| Dagster webserver 포트 | `docs/ports.md`에 신규 예약(예: 12502 후보 — B가 확정·등재) |
| Dagster 메타 DB | `kor_travel_geo_dagster` (env `KTG_DAGSTER_PG_URL`) |
| API observe endpoints | `GET /v1/ops/dagster/summary`, `GET /v1/ops/dagster/runs/{run_id}` |
| API 설정 키 | `KTG_DAGSTER_URL`, `KTG_DAGSTER_ALLOWED_HOSTS`, `KTG_DAGSTER_REPOSITORY_NAME`, `KTG_DAGSTER_REPOSITORY_LOCATION_NAME`, `KTG_DAGSTER_ADMIN_API_URL` |
| GraphQL 쿼리 shape | map `routers/dagster.py`의 summary/run-detail 쿼리 이식(참조) |
| `load_jobs` 신규 필드 | `executor`, `orchestrator_run_id`, `lease_expires_at` |
| launchRun 계약 | jobName + repository/location + `runConfigData.ops.<op>.config` |

## 2. Milestone & task 분해

### M1 — Foundation (병렬)
| task | 담당 | 내용 | 의존 |
|---|---|---|---|
| **T-290a** | A | `kortravelgeo_dagster` 패키지 스캐폴드 + pyproject + `definitions.py` + `resources.py`(engine/rustfs/settings, 4-way fallback) + `mv_refresh` `@op`/`@job`(배선 증명) | contract |
| **T-290b** | B | Dagster 배포: `dagster.yaml`·멀티스테이지 Dockerfile·docker-manager compose(db-init/webserver/daemon)·`kor_travel_geo_dagster` DB·포트 예약(`docs/ports.md`) | T-290a(빌드 대상), contract |
| **T-290c** | A | `load_jobs` `executor`/`orchestrator_run_id`/`lease_expires_at` 마이그레이션 + executor별 recovery split + reconciler + 양방향 cancel 골격(**4단계 진입 게이트**) | — |

M1 완료 게이트: Dagster webserver/daemon 기동, `mv_refresh`가 Dagster run으로 성공, recovery/reconciler 단위 테스트 green. **live e2e 없음**(사용자 대면 표면 아직 없음 — smoke만).

### M2 — 관측 + scheduled backup 온램프 (병렬)  →  ★ live UI e2e #1 게이트
| task | 담당 | 내용 | 의존 |
|---|---|---|---|
| **T-290d** | B | API GraphQL observe 라우터 `/v1/ops/dagster/{summary,runs/{id}}`(SSRF allowlist, 200-on-outage) + 설정 키 | contract |
| **T-290e** | B | admin `/admin/dagster` 페이지 + client + iframe 임베드 + React Query hooks + 생성 타입 | T-290d |
| **T-290f** | A | scheduled backup `@schedule`(온램프: `/run-due` 호출) + `@run_failure_sensor` + 알림 resource | T-290a |

M2 완료 게이트 → **live UI e2e #1**: n150 배포 후 login → `/admin/dagster`가 summary/runs/iframe 렌더,
scheduled/triggered backup run 가시화, 기존 `/admin/backups` 정상(온램프라 in-process가 실제 실행).
Chromium/Firefox read-only. (§3 절차)

### M3 — backup 실행 이관(목표) + verify/copy/drill  →  ★ live UI e2e #2
| task | 담당 | 내용 | 의존 |
|---|---|---|---|
| **T-290g** | A | `db_backup`을 Dagster 실행으로(op이 `run_backup_job()` 호출, `load_jobs` progress 갱신) + verify/copy/restore_drill `@job` | T-290c, T-290f |
| **T-290h** | B | `/admin/dagster` run detail에 backup op 로그·artifact 링크 연결 + 실패/overdue 알림 UI | T-290e, T-290g |

M3 게이트 → **live UI e2e #2**: backup이 Dagster run으로 실행, artifact 다운로드, run/op 로그 admin 가시화.

### M4 — restore 실행 이관(새 빈 DB) — hot-swap은 수동 유지  →  ★ live UI e2e #3
| task | 담당 | 내용 | 의존 |
|---|---|---|---|
| **T-290i** | A | `db_restore`(새 빈 DB)를 Dagster 실행(op이 `run_restore_job()` 호출). **hot-swap/`replace_current`는 Dagster 미실행 — plan/observe만, 기존 guarded API 유지**. RetryPolicy off | T-290c, T-290g |

M4 게이트 → **live UI e2e #3(비파괴)**: restore-to-새DB가 Dagster로 실행, hot-swap plan은 렌더만(미실행).

### M5 — full-load/loader 실행 이관 + in-process 큐 은퇴  →  ★ live UI e2e #4(최종 회귀)
| task | 담당 | 내용 | 의존 |
|---|---|---|---|
| **T-290j** | A | loader(juso/locsum/navi/parcel_link/shp) + `full_load_batch`(main-lib `batch_dag` 호출, map 미러) Dagster 실행 | T-290i |
| **T-290k** | A | in-process 큐/외부 cron/이벤트루프 우회(`_run_loader_off_event_loop`·drain nudge·lifespan 일괄 처리) 은퇴, ADR-006/011 superseded 표기 | T-290j |
| **T-290l** | B | live e2e harness/spec를 Dagster 관측 표면까지 확장, 최종 회귀 suite 정리 | 각 e2e 게이트 |

M5 게이트 → **live UI e2e #4(최종)**: full-load가 Dagster로 실행, in-process 큐 은퇴. n150 full live
regression(Chromium/Firefox, 현재 233-case 기준 + dagster-admin 신규 spec) green.

### M6 — 통합 브랜치 → main 머지
전 milestone·전 e2e green 확인 후 `agent/claude-dagster-migration` → main PR 머지.

## 3. Live UI e2e 계획 (게이트별)

- **실행 위치/방식**: ADR-065대로 n150 Linux Playwright 우선. n150 headless 브라우저 라이브러리 부재로
  이번 배포 사이클에서 불가하면 Windows Playwright를 n150 UI(LAN) 대상 fallback으로 쓰고 사유를 기록한다
  (근거·정본: [live-e2e.md](live-e2e.md)). **참고: n150에서 `sudo npx playwright install-deps chromium
  firefox` 1회면 n150 Linux e2e를 상시화할 수 있다(T-290b에서 함께 처리 권장).**
- **원칙**: 모든 게이트는 **read-only**. 파괴적(backup mutate/rebuild/hot-swap/replace_current)은
  트리거하지 않는다(기존 live spec 규율 준수, `KTG_LIVE_E2E_MUTATE_*` 미설정).
- **게이트 요약**:
  - **#1 (M2)**: `/admin/dagster` 렌더(summary/runs/iframe) + scheduled/triggered backup 가시화. 온램프.
  - **#2 (M3)**: backup을 Dagster run으로 실행·관측, artifact 다운로드.
  - **#3 (M4)**: restore(새 DB) Dagster 실행, hot-swap plan 렌더만.
  - **#4 (M5)**: full-load Dagster 실행 + in-process 큐 은퇴, 전체 회귀(233+ + dagster spec).
- 각 게이트에서 배포 절차·검증은 [deploy-runbook.local.md](deploy-runbook.local.md)(민감, 로컬) 준용.

## 4. 재검증 (회귀 방지)

- 각 실행-이관 task(T-290g/i/j)는 **기존 테스트를 그대로 물린다**: `test_backup_restore_roundtrip`,
  `test_backup_restore_hot_swap_roundtrip`, `test_backup_restore_fault_injection`, `test_restore_reconcile`,
  `test_job_queue` 등. leaf를 재사용하므로 대부분 그대로 통과해야 하며, 실패는 배선 문제로 좁혀진다.
- 백엔드 gate(WSL ext4 미러): `pytest -q`, `ruff`, `mypy src/kortravelgeo`, `lint-imports`,
  `export_openapi --check`. 프론트: `frontend_check.sh`, React Doctor. (CLAUDE.md 빠른 검증 명령 준용)

## 5. 상태 추적

진행/다음-한-작업은 [resume.md](resume.md), 열린 task는 [tasks.md](tasks.md)의 T-290 블록이 정본.
milestone 완료·e2e 결과는 [journal.md](journal.md)에 역시간순 기록.
