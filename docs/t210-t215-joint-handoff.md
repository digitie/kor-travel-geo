# T-210·T-213~T-215 공동(A+B) 작업 핸드오프

작성: Agent B(Claude Code), 2026-06-14. 대상: phase ② 마무리 공동 작업(Codex=Agent A + Claude=Agent B).

## 1. 현재 상태 — phase ② 백엔드·통합 완료

T-109 ② "데이터 적재/백업" **백엔드 + UI + 백엔드 통합**이 모두 main에 머지·검증됨(Agent B, 17 PR).

| 영역 | Task | 상태 |
|------|------|------|
| ops 스키마/migration + full-prefix rename | T-200 | ✅ #134, #159 |
| category catalog + 레거시 제거 | T-201 | ✅ #136 |
| admin role gate | T-202 | ✅ #135 |
| upload session(lifecycle/register/recompute/validator/janitor/restore) | T-203a/b/c | ✅ #139/#142/#145 |
| RustFS reconciliation | T-204 | ✅ #149 |
| match set + rebuild-db bridge | T-205a/b | ✅ #151/#152 |
| consistency registry(C1~C17) + run-validation | T-206 | ✅ #153 |
| backup manifest + restored_from_backup | T-208 | ✅ #154 |
| Admin UI /admin/source-files | T-209 | ✅ #156 |
| 관측성 metric + capacity card | T-211 | ✅ #157 |
| 보존 정책 ADR-052 + bulk hard-delete | T-212 | ✅ #158 |
| **백엔드 통합 스위트(라이브 DB, 18 시나리오)** | T-210(부분) | ✅ #162 |

phase ①(원천 보강·검증 T-110~T-123)은 Agent A가 완료. 두 phase의 인터페이스(C11~C17 registry seed, prototype↔run-validation 회귀 bridge)는 T-206에서 연결됨.

### 통합에서 발견·수정한 런타임 버그 2건(#162)
라이브 PostGIS end-to-end 실행으로 단위 테스트(순수 로직)·CI(DB skip)가 못 잡은 버그를 잡음:
1. 6개 source 서비스의 audit insert가 `ops.audit_events` 스키마(`payload_hash NOT NULL`, `outcome` enum) 위반 → 런타임 IntegrityError. 공통 `infra/source_audit.py`로 수정.
2. `soft_delete_group`이 group을 `validating`으로 남기던 propagation 버그 수정.

## 2. 신규 파이프라인 인터페이스(공동 작업의 계약)

전국 적재는 다음 흐름으로 동작한다(모두 구현·통합 검증됨):

```
업로드 세션 생성 → multipart 업로드 → register(→ ops.source_file_groups/source_files,
  group_sha256, members) → match set 구성/validate/activate(atomic swap)
  → rebuild-db(POST /v1/admin/source-match-sets/{id}/rebuild-db)
      → 적재 전 무결성 게이트(RustFS head/sha 재검증)
      → 기존 full_load_batch DAG enqueue(JobQueue) → SHP/text 로더(GDAL) 적재
      → consistency 게이트(ERROR 차단; forced_promotion은 ERROR만 우회)
      → mv_refresh/swap → serving release + dataset_snapshots.source_match_set_id FK
```

- `infra/source_rebuild_service.py`가 match set → `full_load_batch` payload(기존 `batch_children` 구조) 조립 후 기존 로더 DAG 재사용.
- 로더 자체(juso_text/locsum/navi/shp_polygons/roadaddr_entrance/sppn_makarea)는 phase ① 이전부터 존재. rebuild-db는 그 위의 bridge.

## 3. 남은 공동(A+B) 작업과 필요 환경

아래는 **전국 실데이터 + GDAL 로더 + 스토리지 + (T-063) 하드웨어**가 필요해 단독 환경에서 마칠 수 없는 부분이다.

| Task | 남은 범위 | 필요 환경 | 제안 분담 |
|------|-----------|-----------|-----------|
| **T-210(잔여)** | rebuild-db가 실제 SHP/text 로더로 전국 적재되는 loader 통합, 장비 비종속 perf(deep rehash·multipart 대용량 회귀), `KTG_SLOW_REAL_DATA` 실데이터 | GDAL(`[loaders]`), 전국 `data/juso`, 스토리지(RustFS 또는 local) | B: 신규 파이프라인(완료) · A: 로더/실데이터 실행 |
| **T-213** | 전국 라이브 로딩(신규 파이프라인으로 full load), T-027 행수(≈6,416,642 / 6,416,642 / 24,204) 동치 + snapshot FK 검증 | 위 + 수 시간 적재 | A+B(B 주도 흐름, A 로더/데이터) |
| **T-214** | full load/MV/multipart/deep-rehash/쿼리 벤치(T-047/T-035 harness) | T-213 적재 DB | A+B |
| **T-215** | 튜닝 재측정, geocode/reverse 정확도·v1(vworld)/v2 회귀·C1~C17 정합성 최종 확인, N150/Odroid 실측(T-063 연계), T-109 전체 acceptance | T-214 + 실장비(T-063 보류) | A+B |

## 4. 권장 첫 공동 스텝 + 검증 환경

- **검증 환경(ADR-041, 사용자 지시)**: 실행은 WSL, git·Playwright만 Windows. WSL venv `~/ktgvenv`(`pip install -e "/mnt/f/dev/kor-travel-geo-claude[api,dev]"`; 로더 실행 시 `[loaders]`+시스템 GDAL 추가 필요). 라이브 DB는 WSL Docker `postgis/postgis:16-3.5` `-p 15434:5432`(DSN `postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo`). DB-backed 테스트는 `KTG_TEST_PG_DSN` 설정 시 실행, 미설정 시 skip(CI 무영향).
- **권장 순서**: (1) GDAL 포함 WSL 로더 환경 구성 → (2) **소규모(예: 세종 1개 시도) 실데이터로 신규 파이프라인 end-to-end(업로드→register→match set→rebuild-db→serving) 검증** → (3) 전국 라이브 로딩(T-213) → (4) 벤치(T-214) → (5) 튜닝·acceptance(T-215). N150/Odroid 실측(T-215의 일부)은 하드웨어(T-063) 준비 시.

이 핸드오프 기준으로 Agent A(로더/실데이터)와 Agent B(신규 파이프라인, 완료)가 T-213~T-215를 공동 진행하면 된다.
