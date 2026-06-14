# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-06-14 (T-109 추가 결정 2건 — 자동탐지 제거 / epost 수동 server-fetch)

**작업**: 사용자 결정 2건을 `docs/t109-backup-source-upload-management.md`에 반영했다.

**반영**:
- **자동탐지(`guess_source_kind`) 제거**: "충돌 지점 #1"을 "호환 유지" migration에서 **자동탐지 기능 제거 + 명시 category 업로드 단일화**로 변경했다. source kind는 추정하지 않고 사용자가 고른 category에서 결정론적으로 전개한다. 기존 `/v1/admin/uploads` upload set 흐름은 폐기하고 `/v1/admin/source-files/upload-sessions`로 단일화(admin breaking change, OpenAPI/DTO/CLI/changelog 명시). 요구사항 매트릭스 #1도 갱신했다. 서비스 전이라 호환 alias를 쌓지 않는다.
- **epost 우편번호 자료 수동 server-fetch**: `epost_pobox_full`/`epost_bulk_full`을 "epost 받기" 클릭 → 서버측 다운로드 → RustFS register → `pobox_load`/`bulk_load`로 DB 반영 → 우편번호 검증, 의 별도 수동 흐름으로 정리했다("epost 우편번호 자료" 절 신설). 우편번호는 보조 자료라 `source_match_set` 핵심 rebuild에는 넣지 않고 독립 적재한다. 이 server-fetch는 "자동 다운로드 제외"의 명시적 예외(사용자 클릭 트리거 전용, 자동·스케줄 없음)임을 범위 절에 명시했다.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 시나리오 누락 집중 리뷰 반영)

**작업**: PR #131의 최신 conversation comment `IC_kwDOSW_crs8AAAABGCujRg`를 확인했다. review thread는 여전히 0건이고, 새 코멘트는 head `281bc82` 기준 end-to-end 운영 시나리오 누락 집중 리뷰였다.

**반영**:
- `docs/t109-backup-source-upload-management.md`에 진행 중 upload session 목록/재개 API와 UI "재개 가능한 업로드"를 추가했다.
- RustFS object가 registry 등록 대기 중인 정상 상태를 `pending_registration`으로 분리하고, `registration_deadline_at` 전에는 deletion 후보가 아니라고 명시했다.
- match set state에 `revalidatable`을 추가하고, `activate` atomic swap, active match set invalid의 의미(serving 장애가 아니라 재구성 가능성 결손), invalid 복구 전이를 문서화했다.
- `rebuild-db`에 전역 advisory lock, stale running job 실패 마감, staging 재초기화, consistency ERROR 승격 차단, `forced_promotion=true` 강제 승격 감사 규칙을 추가했다.
- 백업 복원 후 `restored_from_backup` match set은 manifest item별 `missing` stub group/file을 생성하고, source object availability 확인 전에는 rebuild 입력으로 활성화하지 않는 lifecycle을 추가했다.
- ADR-049, `docs/tasks.md`, `docs/resume.md`, 테스트 계획을 새 시나리오 계약에 맞춰 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 추가 코멘트 재확인 — T-109 시나리오 누락 검토)

**작업**: PR #131의 최신 conversation comment와 review thread 상태를 다시 확인했다. unresolved review thread는 없고, 원격 head `281bc82`의 rebuild 적재 전 무결성 게이트 반영이 최신 추가 코멘트의 핵심이었다. 이 반영을 기준으로 T-109 설계에서 운영 시나리오 누락이 있는지 다시 검토했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`에 "운영 시나리오 커버리지 점검" 표를 추가했다. 업로드 세션 생성, multipart 중단/재개, registry insert 실패, multi-part 누락, RustFS 직접 변경, match set 활성화, rebuild, run-validation, 백업/복원, current source `알수없음`, admin role gate, active 참조 hard-delete 차단까지 구현자가 놓치기 쉬운 분기를 한 표에 묶었다.
- `run-validation`도 optional 자료가 존재하면 materialize 직후와 validator 실행 직전 registry hash/size를 대조하고, mismatch는 `skipped`가 아니라 `failed/source_integrity_mismatch`로 기록하도록 명시했다.
- 백업 복원 후 reconstructed match set은 read-only이며, RustFS source archive 존재와 hash를 확인하기 전까지 rebuild 입력으로 바로 활성화할 수 없다고 보강했다.
- ADR-049에 `rebuild-db`/`run-validation` 사용 직전 무결성 게이트를 확정 결정으로 추가했다.
- `docs/tasks.md`와 `docs/resume.md`에 이번 시나리오 커버리지 검토 결과를 반영했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 잔여 finding 반영 — rebuild 적재 전 무결성 게이트)

**작업**: PR #131 head `94188b0` 검토 결과 직전 forward-looking 리뷰(H1~H5, M1~M7, L1~L6)는 거의 모두 반영돼 있었고, 한 가지 남은 finding을 보강했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`의 `rebuild-db` 처리 흐름에 **적재 전 무결성 게이트**(3단계)를 추가했다. 업로드(`register`)와 rebuild 사이 시간차 동안 RustFS object가 교체·손상될 수 있으므로, 다운로드한 archive의 SHA-256/size를 registry `ops.source_files.sha256`/`group_sha256`와 적재 직전 재대조하고, 불일치 시 rebuild 중단 + `quarantined`/`invalid` 전환한다. reconciliation 정기 full 재해시와 별개로 rebuild가 자체 보장한다.
- 같은 원칙을 `run-validation`에도 적용(불일치 시 검증 입력을 `skipped`가 아니라 `failed`로 기록)하도록 명시했다.
- 통합 테스트 목록에 "object 교체 후 rebuild → 무결성 게이트가 mismatch를 잡아 적재 중단" 케이스를 추가했다.

**배경**: 업로드/매칭/적재 3단계가 비연속(업로드만 하고 나중에 적재)인 운영 모델에서, 적재 직전 무결성 재대조가 없으면 시간차 동안 변조된 object가 그대로 적재될 수 있다는 리뷰 지적을 반영한 것이다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 추가 리뷰 반영 — T-109 구현 지침 보강)

**작업**: PR #131 head `3e223a4` 기준 추가 리뷰 코멘트의 H1~H5, M1~M7, L1~L8을 `docs/t109-backup-source-upload-management.md`에 반영했다.

**반영**:
- fresh `ktgctl init-db`가 Alembic head와 drift 나지 않도록 `infra/sql.py` `SCHEMA_SQL`/`INDEX_SQL`, `sql/ddl/001_schema.sql`, Alembic을 함께 갱신하라는 구현 지침과 테스트를 추가했다.
- C11+ case registry schema를 기존 `ConsistencyCaseDefinition` DTO에서 seed 가능한 컬럼으로 재정렬하고 `ops.consistency_case_inputs` link table을 추가했다.
- `user_yyyymm`은 group 단일 정본으로 두고 child/item 중복 기준월을 제거했다.
- `sido_file_set` 고정 모델을 `multi_part` + `part_kind`/`part_key`로 일반화했다.
- upload session/part 진행 상태를 `ops.source_upload_sessions`/`ops.source_upload_session_parts`로 영속화하고 orphaned multipart reconciliation을 추가했다.
- admin role gate의 신원 source를 trusted proxy header 기반 `RequestContext`로 구체화했다.
- RustFS reconciliation은 정기 `quick` scan과 손상 의심/수동 `deep` scan으로 나누고, register 단계의 중복 본문 재읽기를 줄이도록 정리했다.
- rebuild-db 흐름은 download/materialize 병렬·파이프라인과 DB COPY 직렬 유지로 구분했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (ADR-049 — T-109 구현 방향 확정)

**작업**: 사용자 결정에 따라 T-109의 미결정 선택지를 확정하고 문서에 반영했다. 호환성·최소수정보다 확장성, 완성도, 일관성, 성능을 우선하는 방향으로 고정했다.

**반영**:
- `docs/decisions.md`에 ADR-049를 추가했다.
- C11+ case metadata는 DB registry 기반 동적 catalog로 확정했다.
- match set과 운영 snapshot 연결은 `ops.dataset_snapshots.source_match_set_id` FK로 확정했다.
- source file 검증 상태는 `state`와 `validation_state` 분리로 확정했다.
- upload/register 흐름은 storage-first로 확정하되, upload session 생성 시 `user_yyyymm`은 반드시 사용자가 직접 입력·확정한 값으로 받는다. UI는 추정값 또는 현재 날짜 기준 `YYYYMM`을 입력 필드의 사전 입력값으로만 제안하고, 값이 없으면 백엔드가 세션 생성을 거부한다.
- admin role gate, full-prefix `ops` ID rename, `ops.source_file_groups`, multipart/resumable upload, RustFS full object rehash를 구현 기준으로 확정했다.
- `docs/t109-backup-source-upload-management.md`, `docs/tasks.md`, `docs/resume.md`를 ADR-049 기준으로 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 리뷰 반영 — T-109 source group 모델 보강)

**작업**: PR #131 리뷰 코멘트의 M1~M12와 L1~L11을 `docs/t109-backup-source-upload-management.md`에 반영했다. SHP 3종(`electronic_map_full`, `roadaddr_entrance_full`, `zone_shape_full`)은 묶음 ZIP이 아니라 시도별 개별 ZIP 17개를 하나의 group으로 관리하는 모델로 확정했다.

**반영**:
- `ops.source_file_groups`를 match set 참조 단위로 추가하고, `sido_file_set` category는 group 하나 아래 child `ops.source_files` 17행을 보존하도록 정리했다.
- 전자지도 구조 검증은 11개 layer 필수, serving load는 현행 9개 layer로 분리했다.
- C11+ case CHECK 완화, RustFS client 확장, upload session 상태 매핑, SSE event schema, destructive admin action 권한/감사, 운영 용량 관리, 백업 manifest group 구조를 문서에 추가했다.
- 권고안 선택지가 있는 항목은 장단점 표로 남기고, 최종 결정이 필요한 항목을 후속 ADR 후보로 분리했다.
- `docs/tasks.md`와 `docs/resume.md`의 T-109 대기/재개 설명도 `source_file_group` 모델 기준으로 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (백업 원천 파일 업로드·매칭·검증 관리 고도화 설계)

**작업**: 백업/리스토어 고도화의 원천 파일 관리 흐름을 구현 전에 문서화했다. 사용자 요구사항에 따라 파일 업로드는 category별 명시 slot으로 나누고, 기준년월은 사용자가 직접 확정하며, 정상 업로드 파일 metadata는 DB registry에서 관리하고, RustFS object와 DB row의 정합성 검증/복구를 admin UI에서 처리하는 방향으로 설계했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`를 추가했다.
- `docs/tasks.md`에 T-109 구현 대기 항목을 등록했다.
- `docs/resume.md`에 문서화 완료와 구현 대기 상태를 추가했다.
- `docs/backup-restore-source-inventory.md`에서 T-109 설계 문서를 참조하게 했다.

**핵심 결정/주의**:
- 사용자 요청의 기본 category 목록은 맞지만, `도로명주소 한글_전체분`은 내부적으로 `juso`와 `parcel_link` 두 source kind를 만들고, `도로명주소 출입구 정보`와 `구역의도형`은 현행 코드에서는 optional이므로 `serving_minimal`과 `serving_recommended` profile을 분리하도록 제안했다.
- `건물군 내 상세주소 동 도형`, `도로명주소 건물 도형`, `국가지점번호 도형/중심점`, `민원행정기관전자지도`는 match set의 optional 검증/보강 자료로 관리하고 C11+ 검증 케이스를 추가하는 방향으로 정리했다.
- incremental 업데이트 파일 업로드는 T-109 범위에서 명시적으로 제외했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (미사용 원천 데이터 정확도 개선 검토)

**작업**: `F:\dev\kor-travel-geo\data\juso` 현재 배치에서 기본 full-load가 쓰지 않거나 선택/조건부로만 쓰는 원천을 대상으로, 직접 정확도 개선 가능성·검증용 가치·도입 위험을 문서화했다.

**반영**:
- `docs/source-data-accuracy-review.md`를 추가했다.
- 국가지점번호 도형/중심점은 현 10m 국가지점번호 parser보다 더 정밀한 좌표 원천은 아니지만, 100m 이하 prefix 검증·formatter regression·grid overlay에는 가치가 있음을 정리했다.
- `도로명주소 건물 도형`은 출입구 point/연결선 검증과 후보 scoring 개선에는 가치가 있지만 `TL_SPBD_BULD` 대체재가 아니므로 별도 analysis table부터 시작해야 한다고 정리했다.
- `건물군 내 상세주소 동 도형`과 `상세주소DB`는 일반 주소 geocode가 아니라 상세주소 기능/검증 후보로 분리했다.
- `주소DB`, `건물DB`, `민원행정기관전자지도`, 과거 snapshot, 전자지도 내부 미사용 layer, 내비 `match_jibun_*`의 활용 가능성과 검증용 가치를 함께 정리했다.

**검증**:
- PowerShell/Python ZIP·DBF header 스캔과 WSL `7z` 조회로 파일 구조, record count, 중심점 분포를 확인했다.

## 2026-06-14 (원본 디렉터리 사용/미사용 구분)

**작업**: `F:\dev\kor-travel-geo\data\juso` 현재 배치 기준으로 full-load 사용, 선택/조건부 사용, 기본 서빙 load 미사용 파일을 구분해 백업/리스토어 원천 인벤토리에 추가했다.

**반영**:
- `202605_도로명주소 한글_전체분.zip`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분.7z`, `도로명주소 전자지도\202604\<시도>.zip`을 기본 full-load 사용 원천으로 정리했다.
- `도로명주소 출입구 정보\202604\<시도>.zip`과 `구역의도형\202603\<시도>.zip`을 선택/조건부 사용 원천으로 분리했다.
- 상세주소DB, 주소DB, 건물DB, 도로명주소 건물 도형, 건물군 내 상세주소 동 도형, 국가지점번호 grid/중심점, 민원행정기관전자지도는 현행 기본 서빙 load에서 쓰지 않는 원천으로 명시했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (로컬 원본 파일 재스캔과 전자지도 ZIP 확인)

**작업**: `F:\dev\kor-travel-geo\data\juso`에 추가 정리된 원본 파일을 다시 스캔해, full-load 필수 원천과 선택 원천의 압축파일 기준 위치와 기준년월 추출 가능성을 갱신했다.

**반영**:
- `도로명주소 전자지도\202604\<시도>.zip` 17개 안에 serving 대상 9개 SHP layer의 `.shp/.shx/.dbf` sidecar가 모두 있음을 확인하고 문서화했다.
- `TL_SPRD_MANAGE`, `TL_SPRD_INTRVL`, `TL_SPRD_RW`, `TL_SPBD_BULD`의 원본이 `도로명주소 전자지도\202604\<시도>.zip`임을 명시했다.
- `도로명주소 출입구 정보\202604`의 내부 파일은 `RNENTDATA_2605_*`라서 내부 파일명 기준월은 `202605`임을 주의사항으로 남겼다.

**검증**:
- PowerShell/.NET ZIP 리더와 WSL `7z` 목록 조회로 압축파일 내부 member 수를 확인했다.

## 2026-06-14 (백업/리스토어 원천 데이터 인벤토리 문서화)

**작업**: 백업/리스토어 로직 고도화를 위해 현재 로더가 사용하는 파일 원천, 외부 API 소스, 파생 MV/accelerator, manifest 권장 필드를 별도 문서로 정리했다.

**반영**:
- `docs/backup-restore-source-inventory.md`를 추가했다.
- full-load 필수 source kind(`juso`, `parcel_link`, `locsum`, `navi`, `shp`)와 선택 source kind(`roadaddr_entrance`, `sppn_makarea`, `pobox`, `bulk`)의 파일 패턴과 적재 테이블을 정리했다.
- VWorld/Juso는 조회 폴백, epost는 오프라인 ZIP 원천 생성 API, RustFS는 source provider가 아니라 upload set 저장소라는 경계를 명시했다.

**검증**:
- 문서-only 변경. 별도 테스트는 실행하지 않았다.

## 2026-06-13 (로컬·Docker API/UI 포트 1250x 통일)

**작업**: 사용자 지시에 따라 로컬 단독 실행 포트를 Docker 실행·`kor-travel-docker-manager` scrape target과 같은 `12501`/`12505`로 맞췄다.

**반영**:
- FastAPI 기본 실행 포트와 API Dockerfile `PORT`/`EXPOSE`를 `12501`로 변경했다.
- `kor-travel-geo-ui` 기본 실행 포트, UI Dockerfile `PORT`/`EXPOSE`, Playwright 기본 `baseURL`, UI proxy 기본 `KTG_API_INTERNAL_URL`을 `12505`/`12501` 기준으로 변경했다.
- `scripts/docker_app.sh`, `scripts/deploy_app.py`, `scripts/benchmark_api_latency.py`의 기본 포트를 `12501`/`12505`로 변경했다.
- `docs/ports.md`, `docs/dev-environment.md`, README, UI README, API reference, `docs/resume.md`를 현재 실행 기준으로 갱신하고 ADR-048을 추가했다. ADR-046은 superseded로 남겼다.
- 주변 서비스 포트도 `kor-travel-docker-manager`의 `docs/ports.md`, `AGENTS.md`, `docker-compose.yml`을 기준으로 맞췄다. PostgreSQL `5432`, RustFS API/console `12101`/`12105`, Grafana/cAdvisor/Prometheus `12205`/`12301`/`12401`, concierge `12601`/`12602`/`12605`, map `12701`/`12702`/`12705`, Pinvi `12801`/`12805`, manager `12901`/`12905`를 `docs/ports.md`에 정리했다.
- RustFS 관련 테스트 fixture의 예시 endpoint도 이전 `9003`에서 manager 기준 `12101`로 변경했다.

**검증**:
- Windows/NTFS: `python -m pytest tests/unit/test_deploy_app.py tests/unit/test_rustfs_uploads.py -q` → `orjson` 미설치로 `test_rustfs_uploads.py` 수집 실패. WSL ext4 미러 가상환경 검증을 기준으로 삼았다.
- Windows/NTFS: `python -m ruff check scripts/deploy_app.py scripts/benchmark_api_latency.py tests/unit/test_deploy_app.py` → pass
- Windows/NTFS: `git diff --check` → pass
- WSL ext4 mirror: `.venv/bin/python -m pytest -q` → 298 passed, 25 skipped
- WSL ext4 mirror: `.venv/bin/python -m ruff check .` → pass
- WSL ext4 mirror: `.venv/bin/python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `.venv/bin/lint-imports` → Layered architecture kept
- WSL ext4 mirror: `.venv/bin/python -m pytest tests/unit/test_deploy_app.py tests/unit/test_rustfs_uploads.py -q` → 13 passed
- WSL ext4 mirror: `.venv/bin/python -m ruff check scripts/deploy_app.py scripts/benchmark_api_latency.py tests/unit/test_deploy_app.py` → pass
- WSL ext4 mirror `kor-travel-geo-ui`: `npm run lint`, `npm run test`, `npm run build` → pass
- WSL ext4 mirror `kor-travel-geo-ui`: `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0
- 실제 서버: API `http://127.0.0.1:12501/v1/healthz` → `{"status":"ok"}`
- 실제 서버: UI `http://127.0.0.1:12505/debug/geocode` → HTTP 200
- 실제 서버: UI proxy `http://127.0.0.1:12505/api/proxy/v1/healthz` → `{"status":"ok"}`
- CodeGraph: `codegraph sync`, `codegraph status` → `disk I/O error`로 실패

## 2026-06-13 (T-108 운영 배포 자동화)

**작업**: 사용자 지시에 따라 `pinvi`의 T-108을 이 저장소 작업 항목으로 가져오고, API/UI 운영 배포 자동화 표면을 구현했다.

**반영**:
- `docs/tasks.md` 완료 섹션에 T-108을 등록하고, `docs/t108-deploy-automation.md`에 `pinvi` 원문을 보존했다.
- `scripts/deploy_app.py`를 추가했다. `plan`은 build/deploy 계획 JSON·Markdown을 만들고, `build`는 API/UI `docker buildx build` 멀티플랫폼 명령을 실행하며, `deploy`는 N150/Odroid 같은 원격 노드에 SSH로 API/UI 컨테이너를 배포한다.
- 원격 배포는 노드의 `--env-file`을 사용해 `KTG_PG_DSN`, `KTG_RUSTFS_*`, `KTG_VWORLD_API_KEY`를 주입하며 secret 값을 명령행에 펼치지 않는다.
- PostgreSQL/RustFS 생명주기는 이 저장소에서 관리하지 않으며, 사용자 추가 지시에 따라 streaming replication은 이번 범위에서 제외했다.
- `docs/t108-deploy-automation.md`, `docs/resume.md`, `CHANGELOG.md`를 갱신했다.

**검증**:
- Windows/NTFS: `python -m pytest tests/unit/test_deploy_app.py -q` → 6 passed
- Windows/NTFS: `python -m ruff check scripts/deploy_app.py tests/unit/test_deploy_app.py` → pass
- Windows/NTFS: `python scripts/deploy_app.py plan --tag test --output-dir .tmp\t108-plan` → plan 생성 확인
- Windows/NTFS: `git diff --check` → pass
- WSL ext4 mirror: `python -m pytest -q` → 298 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept
- WSL ext4 mirror: `python scripts/deploy_app.py plan --tag test --output-dir /tmp/ktg-t108-plan` → JSON/Markdown 생성 확인

## 2026-06-13 (Prometheus 상세 계측 범위 확장)

**작업**: 사용자 요청에 맞춰 API, Next.js admin UI, provider/load batch job 단계, DB query별 성능 측정을 추가했다.

**반영**:
- SQLAlchemy event hook 기반 DB query counter/duration histogram을 추가하고, query 원문 대신 operation과 fingerprint를 label로 사용한다.
- load job 전체 duration과 stage별 duration histogram을 추가했다.
- `kor-travel-geo-ui`에 `/api/metrics` Prometheus endpoint, `/api/metrics/web-vitals` 수집 endpoint, Web Vitals reporter, Next.js route handler/proxy upstream duration 계측을 추가했다.
- `kor-travel-docker-manager` Prometheus scrape target을 `kor-travel-geo-api:12501/metrics`, `kor-travel-geo-ui:12505/api/metrics` 기준으로 맞췄다.

**검증**:
- WSL ext4 mirror: `.venv/bin/python -m pytest -q` → 292 passed, 25 skipped
- WSL ext4 mirror: `.venv/bin/python -m ruff check .` → pass
- WSL ext4 mirror: `.venv/bin/python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `.venv/bin/lint-imports` → Layered architecture kept
- WSL ext4 mirror `kor-travel-geo-ui`: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` 통과
- WSL ext4 mirror `kor-travel-geo-ui`: `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0

## 2026-06-13 (Prometheus 성능 모니터링 보강)

**작업**: `kor-travel-docker-manager`의 관측 스택 포트 정책을 확인해 `kor-travel-geo` API `/metrics`의 성능 메트릭을 보강했다. Prometheus는 앱이 능동 연결하지 않고 외부 scraper가 `/metrics`를 가져가는 pull 구조로 유지한다. Docker manager 기준 Prometheus/Grafana/cAdvisor host 포트는 `12401`/`12205`/`12301`이고, compose 내부 API scrape target은 `kor-travel-geo-api:12501/metrics`다.

**반영**:
- `kor_travel_geo_api_requests_total`, `kor_travel_geo_api_slow_requests_total`, `kor_travel_geo_api_requests_in_progress`를 추가했다.
- SQLAlchemy pool 상태 gauge `kor_travel_geo_pg_pool_size`, `kor_travel_geo_pg_pool_checked_in`, `kor_travel_geo_pg_pool_checked_out`, `kor_travel_geo_pg_pool_overflow`를 추가했다.
- `/metrics` 요청 시 cache/load job gauge와 함께 DB pool gauge를 갱신한다.
- `README.md`, `.env.example`, `docs/architecture.md`, `docs/ports.md`, `CHANGELOG.md`에 Prometheus/Grafana 포트와 pull 방식 scrape target을 문서화했다.

**검증**:
- WSL ext4 mirror: `python -m pytest -q` → 290 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept

## 2026-06-13 06:20 (T-077 `kor-travel-geo` 식별자 전환 구현)

**작업**: 사용자 확정값에 맞춰 프로젝트 식별자를 `kor-travel-geo` 계열로 통일했다. Python import root는 `kortravelgeo`, 권장 alias는 `import kortravelgeo as ktg`, CLI는 `ktgctl`, 환경변수 prefix는 `KTG_*`, PostgreSQL 기본 DB명은 `kor_travel_geo`, RustFS bucket/prefix 기본값은 `kor-travel-geo`다.

**반영**:
- backend package를 `src/kortravelgeo/`로 옮기고 전체 import, import-linter, mypy, Alembic, OpenAPI export, Docker/uvicorn entrypoint를 갱신했다.
- `pyproject.toml` 배포명은 `kor-travel-geo`, console script는 `ktgctl`로 고정했다.
- `kortravelgeo.__init__`에서 `AsyncAddressClient`, 주요 v2 DTO, `Point`, `ZipSource`, `RegionHint`를 공개해 `import kortravelgeo as ktg` 사용을 고정했다.
- 환경변수는 `KTG_*`로 통일하고 `.env.example`, Settings, Docker 실행 스크립트, UI proxy/runtime config, 문서 예시를 갱신했다.
- PostgreSQL 서비스 DB를 `kor_travel_geo`로 rename하고, Docker API/UI를 새 기본 DB명과 RustFS `kor-travel-geo` 기본값으로 재기동했다.
- API request duration Prometheus histogram과 `KTG_API_PERFORMANCE_LOGGING_ENABLED` opt-in 성능 로그를 추가했다. 로그는 route template/method/status/elapsed_ms만 기록하고 query string과 주소 입력값은 남기지 않는다.
- `kor-travel-geo-ui` package로 UI 경로를 옮기고 누락된 `scripts/`, `tests/`, `types/` 파일을 복구했다. React Doctor 지적에 따라 Query 결과 객체 전체 구독을 제거하고 `vitest`를 `4.1.8` 계열로 갱신했다.
- `docs/t077-kor-travel-geo-rename.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`, ADR-047을 갱신했다.

**검증**:
- 이전 이름 계열 내용 검색 2회 → 0건
- 이전 이름 계열 파일/디렉터리명 검색 2회 → 0건
- 잘못된 CLI 실행 예시 검색 2회 → 0건
- WSL ext4 mirror: `python -m pytest -q` → 289 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept
- WSL ext4 mirror UI: `npm run gen:types`, `lint`, `type-check`, `test`, `build` → pass
- WSL ext4 mirror UI: `npx react-doctor@latest . --offline --verbose --json` → score 100, diagnostics 0
- Docker: `scripts/docker_app.sh build && scripts/docker_app.sh up` → API `12201`, UI `12205`
- Smoke: `GET /v1/healthz` → `ok`; `/v2/geocode` 인사동 → `OK` 후보 10건; `/v2/reverse` 인사동 좌표 → `OK` 후보 10건; UI runtime VWorld key non-empty; API/UI restart policy `unless-stopped`

## 2026-06-12 09:55 (T-077 배포명·임포트명 전환 Task 문서화)

**작업**: 사용자 지시에 따라 Python 배포명 `kor-travel-geo`, import root `kortravelgeo`, 권장 alias `import kortravelgeo as ktg` 전환을 후속 Task로 정리했다.

**반영**:
- `docs/tasks.md`의 대기 항목에 T-077을 추가했다.
- `docs/t077-kor-travel-geo-rename.md`를 추가해 목표 식별자, 범위, 범위 밖, 호환성 원칙, 구현 체크리스트, 검증 기준, 남은 결정을 정리했다.
- 현재 코드와 실행 문서는 아직 `kor-travel-geo`/`kortravelgeo` 기준으로 유지한다. 실제 rename은 후속 구현 PR에서 원자적으로 처리한다.

**검증**:
- 문서-only 변경으로 `git diff --check`를 실행한다.

## 2026-06-12 09:20 (로컬 고정 포트 재정의와 Docker 재기동)

**작업**: 사용자 지시에 따라 PostgreSQL `5432`, RustFS API `12101`, 이 저장소 API `12201`, Web UI `12205`를 현재 고정 포트로 정리했다.

**반영**:
- `scripts/docker_app.sh`의 API/UI host/container 기본 포트를 `12201`/`12205`로 변경했다.
- API/UI Dockerfile의 내부 `PORT`/`EXPOSE`를 각각 `12201`/`12205`로 변경했다.
- `.env.example`, UI proxy 기본값, Playwright 기본 base URL, API reference, README, 현재 운영 문서를 새 포트 기준으로 갱신했다.
- `/admin/settings` RustFS endpoint placeholder를 `http://127.0.0.1:12101`로 변경했다.
- ADR-046을 추가하고 ADR-042의 `9001`/`9002` 결정은 superseded 처리했다.

**검증**:
- `bash -n scripts/docker_app.sh && bash -n scripts/fullload_test.sh`
- `scripts/docker_app.sh build` — API image build와 UI `next build`/TypeScript 통과
- `scripts/docker_app.sh up` — API `12201`, UI `12205`로 재생성
- Docker port/status: PostgreSQL `5432` healthy, RustFS API `12101` healthy, API `12201`, UI `12205`, API/UI restart policy `unless-stopped`
- `GET http://127.0.0.1:12201/v1/healthz` → `ok`
- `POST http://127.0.0.1:12201/v2/geocode` `"서울특별시 종로구 인사동"` → `OK`, 후보 10건
- `POST http://127.0.0.1:12201/v2/reverse` 인사동 좌표(`126.986`, `37.574`, 반경 200m) → `OK`, 후보 10건
- `GET http://127.0.0.1:12205/debug/geocode` → HTTP 200
- `GET http://127.0.0.1:12205/api/runtime-config` → VWorld key non-empty
- `npm run test -- tests/unit/runtime-config.test.ts` → 5 passed
- API image 안에서 `python -m pytest tests/unit/test_settings.py -q` → 5 passed
- API image 안에서 `python -m ruff check alembic/versions/0013_t061_text_search_mv.py scripts/benchmark_api_latency.py src/kortravelgeo/settings.py` → pass

## 2026-06-12 07:45 (WSL 재설치 후 주소 DB 복원과 API/UI 재시작 정책)

**작업**: WSL 재설치 뒤 빈 `kor_travel_geo` DB로 API만 기동되어 다른 에이전트의 reverse/geocode 보강이 모두 결측 처리될 위험을 해소했다.

**반영**:
- `/mnt/f/dev/kor-travel-geo/artifacts/perf/t047-operational-impact-20260528/pgdump-dir.tar.zst` 백업을 임시 DB `kor_travel_geo_restore_t047_20260612`에 복원했다.
- 복원 DB를 Alembic head(`0015_t075_region_radius_parts`)까지 올린 뒤 smoke test를 통과시켜 현재 `kor_travel_geo`로 승격했다. 기존 빈 DB는 `kor_travel_geo_empty_20260612_073529` 이름으로 보존했다.
- `scripts/docker_app.sh`의 API/UI 컨테이너에 기본 Docker restart policy `unless-stopped`를 적용했다. 필요하면 `KTG_DOCKER_RESTART_POLICY=no`로 끌 수 있다.
- `alembic/versions/0013_t061_text_search_mv.py`가 최신 `TEXT_SEARCH_MV_SQL` 상수를 참조해 과거 revision 복원 DB에서 깨지던 문제를 고쳤다. `0013`은 T-061 당시의 MV 정의를 자체 보관하고, `0014`가 T-065 컬럼 추가 후 최신 MV를 재생성한다.

**검증**:
- `bash -n scripts/docker_app.sh`
- `scripts/docker_app.sh build-api`
- 복원 DB에서 `alembic upgrade head` 통과
- DB row count: `tl_juso_text=6,416,637`, `mv_geocode_target=6,416,637`, `mv_geocode_text_search=6,416,637`, `region_radius_parts=54,316`
- API 컨테이너 `restart=unless-stopped`, UI 컨테이너 `restart=unless-stopped`
- `GET /v1/healthz` → `{"status":"ok"}`
- `POST /v2/reverse` 인사동 좌표(`126.986,37.574`, 반경 200m) → `OK`, 후보 반환
- `POST /v2/geocode` `"서울특별시 종로구 인사동"` → `OK`, 후보 반환

**참고**:
- 이번 복원은 최신 full-load가 아니라 T-047 시점 백업을 최신 schema로 올린 운영 복구다. T-073 이후 최신 daily/국가지점번호 재측정 DB가 필요하면 별도 최신 백업 또는 full-load를 다시 적용한다.

## 2026-06-10 21:45 (PostgreSQL/RustFS 구동 책임 제거)

**작업**: 사용자 지시에 따라 이 저장소에서 PostgreSQL/PostGIS와 RustFS의 직접 구동·정지·재시작 책임을 제거했다. 이제 이 프로젝트는 이미 동작 중인 DB와 bucket에 접속해 사용하며, 필요한 접속 정보는 `.env`, 환경변수, 또는 admin UI 설정 파일에 저장한다.

**반영**:
- `docker-compose.yml`을 삭제했다.
- `scripts/docker_app.sh`에서 RustFS 구동/정지/로그 명령을 제거하고, API/UI 컨테이너에 `KTG_PG_DSN`, `KTG_RUSTFS_*` 접속 설정을 주입하는 역할만 남겼다.
- README, AGENTS, SKILL, 개발 환경/포트/복구/작업 재개 문서를 "이미 동작 중인 DB와 bucket 접속 설정" 기준으로 갱신했다.
- ADR-045를 추가하고 ADR-044의 RustFS 구동 책임 내용을 superseded 처리했다.

**검증**:
- `bash -n scripts/docker_app.sh`
- `scripts/docker_app.sh help`

## 2026-06-03 09:16 (RustFS 업로드 저장소와 접속 설정 표준)

**작업**: 업로드 파일을 로컬 디렉터리 대신 RustFS(S3 호환)에 저장할 수 있는 옵션을 추가했다. 당시 포함됐던 RustFS 직접 구동 책임은 2026-06-10 ADR-045로 폐기됐고, 현재 기준은 이미 동작 중인 bucket 접속 설정만 저장하는 것이다.

**반영**:
- `rustfs://<bucket>/<prefix>/...` URI와 `storage_kind="local" | "rustfs"`를 upload set manifest/DTO/API에 추가했다.
- `/v1/admin/storage/rustfs/config`, `/check`, `/import-prefix`, `/sync-local` API를 추가했다. secret은 설정 조회 응답에 원문으로 노출하지 않는다.
- `/admin/settings`에서 RustFS 사용 여부, endpoint, bucket, prefix, region, access/secret key, retention을 설정하고 연결 확인을 실행할 수 있게 했다.
- `/admin/load`에서 업로드 저장소를 선택하고, RustFS prefix import와 기존 로컬 파일 RustFS sync를 실행할 수 있게 했다.
- `kor-travel-geo`/`python-krtour-map`/`tripmate` prefix 분리, 무기한 보존 기본값, Chrome/Firefox Playwright e2e 원칙을 문서화했다.

**검증**:
- ext4 테스트 미러에서 backend `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`를 통과했다. pytest는 `303 passed, 7 skipped`다.
- ext4 테스트 미러에서 frontend `scripts/frontend_check.sh --install`을 통과했다. `gen:types`, lint, type-check, Vitest 42개, build가 모두 성공했다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- `scripts/docker_app.sh build`로 API/UI image를 다시 빌드했고, API build에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- 실제 API + RustFS 접속 테스트에서 `/data/juso/도로명주소 전자지도/서울특별시/11000/TL_SCCO_LI.shp`와 `/data/juso/202604_사서함주소DB_전체분.zip`을 RustFS로 sync하고 prefix import를 확인했다. 직접 `PUT /v1/admin/uploads/{id}/files` RustFS 업로드도 `state=uploaded`로 확인했다.
- Windows Playwright Docker UI `http://localhost:9002`: Chromium 전체 e2e 16 passed, Firefox 전체 e2e 16 passed. 메뉴 반복 이동 테스트는 `This page couldn`, `Reload to try again`, `_rsc` client routing 요청 부재를 확인하고, VWorld 지도 테스트는 실제 WMTS 타일과 MapLibre canvas를 확인한다.

**발견**:
- RustFS는 여러 프로젝트가 공유할 수 있으므로 이 저장소는 구동 책임을 갖지 않고 bucket/prefix 접속 설정만 유지하는 편이 안전하다.

## 2026-06-03 09:15 (antigravity-readme-cleanup)

**작업**: README.md의 가독성과 레이아웃을 GFM 스타일에 맞추어 정돈하였고, docs/agent-guide.md에 포함된 절대경로에서 특정 로컬 사용자명(digit)을 제거하여 개인정보를 마스킹했습니다. 또한 tripmate 등의 특정 프로젝트명 언급 여부를 조사하여 해당 명칭이 저장소에 없음을 확인했습니다.

**반영**:
- `README.md`의 현재 상태(Status Note) 문단을 GFM 리스트 형태로 개조하여 가독성을 향상시켰습니다.
- `README.md` 개발 환경 경로 안내 예시의 텍스트 줄바꿈 정렬 어긋남을 수정했습니다.
- `docs/agent-guide.md`에서 로컬 윈도우 사용자가 노출되던 절대경로 `Users/digit`을 `Users/<user>`로 일반화하여 마스킹했습니다.
- 저장소 전체에서 `tripmate`를 대소문자 구분 없이 검색하였으며, 사용 흔적이 전혀 발견되지 않음을 검증 및 보고합니다.

**검증**:
- 변경사항에 대해 `git diff`를 실행하여 텍스트 포맷과 경로 수정 결과가 안전함을 확인했습니다.
- 변경된 파일은 마크다운(.md) 문서 파일들로, 백엔드 및 프론트엔드의 실행 로직에는 영향을 주지 않습니다.

## 2026-06-03 01:30 (admin UI 메뉴 이동 Next 전역 오류 화면 보정)

**작업**: 좌측 메뉴를 클릭하다가 Chrome/Firefox 모두에서 Next 기본 전역 오류 화면(`This page couldn’t load`, `Reload to try again, or go back.`)으로 떨어지는 현상을 재현·보정했다.

**반영**:
- 좌측 메뉴와 Consistency report 목록의 internal link를 `DocumentNavLink`로 교체했다. `next/link`는 유지하되 `prefetch={false}`와 명시적 document navigation을 사용해 Next App Router client transition/RSC fetch 실패 화면으로 새지 않게 했다.
- 긴 좌측 메뉴가 데스크톱에서 viewport 아래로 밀리는 문제를 막기 위해 sidebar에 `100dvh` 높이와 내부 스크롤을 적용했다.
- VWorld 타일 요청이 페이지 이동 중 브라우저에 의해 취소될 때(`ERR_ABORTED`, `NS_BINDING_ABORTED`) 지도 불안정 overlay 카운트와 warning 로그에 반영하지 않도록 했다.
- 좌측 메뉴 반복 이동 e2e를 추가했다. 이 테스트는 메뉴 15개를 4회 순회하며 Next 전역 오류 문구, page error, 비정상 request failure, `_rsc` client routing 요청 부재를 확인한다.

**검증**:
- `scripts/docker_app.sh build-ui && scripts/docker_app.sh up-ui`로 UI image를 다시 빌드하고 `http://127.0.0.1:9002` 컨테이너를 교체했다.
- Windows Playwright Chromium/Firefox: `tests/e2e/navigation.spec.ts` → 각 1 passed.
- Windows Playwright Chromium/Firefox: `tests/e2e/vworld-map.spec.ts` → 각 2 passed.
- ext4 테스트 미러 Linux Node에서 `npm run lint`, `npm run type-check`, `npm run test`를 통과했다. unit test는 11 files / 42 tests 통과다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.

**발견**:
- 해당 문구는 앱 코드가 아니라 Next 16 기본 `global-error` 화면에서 나온다. 메뉴 전환 중 발생하는 client routing/RSC fetch 실패 화면을 피하려면 내부 운영 UI에서는 안정적인 document navigation이 더 적합하다.

## 2026-06-02 23:58 (`/v2/regions/within-radius` DB 튜닝)

**작업**: 행정구역 반경조회가 큰 polygon을 레벨별로 직접 훑으며 tail latency가 커지는 문제를 줄이기 위해 `region_radius_parts` serving accelerator를 추가했다.

**반영**:
- `region_radius_parts` 테이블과 Alembic `0015_t075_region_radius_parts` migration을 추가했다. `tl_scco_ctprvn/sig/emd`를 `ST_Subdivide(geom, 256)`으로 쪼개고 `level`, `code`, parent code, `part_no`, `geom`을 보관한다.
- `GeometryRepository.regions_within_radius()`는 레벨별 3회 query loop 대신 단일 SQL을 실행한다. 입력점은 한 번만 EPSG:5179로 변환하고, 후보 검색은 `region_radius_parts.geom` GiST index + `ST_DWithin`을 사용한다.
- `contains` 관계는 accelerator 조각이 아니라 원본 `tl_scco_ctprvn/sig/emd`의 `ST_Covers`로 코드 기준 계산한다.
- 시군구 후보는 반경 안의 시도 parent code로, 읍면동 후보는 반경 안의 시군구 parent code로 좁힌다.
- `load shp`, `load shp-all`, `load all-sidos`, `refresh mv` 경로가 accelerator를 다시 채우도록 했다.
- ADR-043, `docs/data-model.md`, v2 API reference, CHANGELOG, resume, task tracker를 갱신했다.

**검증**:
- ext4 테스트 미러에서 `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`를 통과했다. pytest는 `297 passed, 7 skipped`다.
- Docker API image build에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- 실제 T-027 최종 DB는 Alembic table이 없던 운영 적재 DB라 `alembic stamp 0014_t065_navi_name_search` 후 `alembic upgrade head`로 `0015`만 적용했다.
- 실제 DB accelerator row count는 `sido=10,607`, `sigungu=14,686`, `emd=29,023`이고 GiST/parent index 3개와 PK를 확인했다.
- `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo pytest tests/integration/test_optional_real_postgres_regions.py -q` → `1 passed`. 이 테스트는 accelerator 결과와 원본 `tl_scco_*` 직접 `ST_DWithin` 결과를 비교한다.
- `scripts/docker_app.sh up`으로 API `9001`, UI `9002`를 새 이미지로 다시 올렸다. `/v1/healthz`, `/debug/geocode`, `/api/runtime-config`가 200을 반환했고 VWorld 키는 길이만 확인했다.
- REST benchmark 40회 반복:
  - `seoul_3km`: p50 `13.10ms → 13.68ms`, p95 `22.00ms → 20.89ms`, count 동일(`sido=1`, `sigungu=6`, `emd=190`).
  - `seoul_20km`: p50 `39.09ms → 22.80ms`, p95 `122.05ms → 28.61ms`, count 동일(`sido=3`, `sigungu=49`, `emd=645`).
  - `busan_10km`: p50 `38.75ms → 12.28ms`, p95 `45.80ms → 14.89ms`, count 동일(`sido=2`, `sigungu=17`, `emd=138`).

**발견**:
- 기존 T-027 최종 DB는 schema objects는 최신이지만 `alembic_version` table이 없었다. 운영 적재 DB에 migration을 적용할 때는 기존 schema level을 확인한 뒤 stamp 후 upgrade해야 한다.

## 2026-06-02 21:49 (Docker 실행 스크립트, 9001/9002 포트 원칙, Firefox VWorld 지도 보정)

**작업**: API/UI Docker 이미지를 GDAL 버전 매칭 상태로 빌드·실행하는 표준 스크립트를 추가하고, 로컬 API/UI 포트 원칙을 `9001`/`9002`로 갱신했다. Firefox에서 VWorld 지도가 보이지 않는 원인을 확인해 `vworld://` custom protocol fallback을 쓰지 않도록 보정했다.

**반영**:
- `docker/api.Dockerfile`과 `kor-travel-geo-ui/Dockerfile`을 추가·갱신해 API는 `9001`, UI는 `9002`로 실행한다. API image build 중 `gdal-config --version`과 Python `gdal` wheel 버전을 맞추고 불일치 시 실패한다.
- `scripts/docker_app.sh`를 추가해 `build-api`/`build-ui`/`build`/`up-api`/`up-ui`/`up`/`down`/`status`/`logs`/`cli`/`load`/`load-full-set`을 제공한다. 기본 실행은 Docker bridge network이며, `.env`/`kor-travel-geo-ui/.env.local`의 VWorld 키를 컨테이너 환경변수로 주입하되 키 값은 출력하지 않는다.
- `scripts/docker_app.sh up` 계열은 API `9001`, UI `9002` host 포트를 점유한 기존 Docker 컨테이너와 listen 프로세스를 종료한 뒤 새 컨테이너를 올린다.
- Firefox에서 `maplibre-vworld`의 `unsupportedTileFallback`이 타일 URL을 `vworld://...`로 바꾸면 CORS `not http`로 차단되는 것을 확인했다. `CoordinateMap`은 해당 fallback prop을 전달하지 않고 HTTPS WMTS를 직접 사용한다.
- `vworld-map.spec.ts`는 Firefox에서 `/debug/geocode` 반복 진입, runtime VWorld 키, 실제 WMTS tile fetch, MapLibre canvas, 지도 스크린샷 색상 다양성, `vworld://`/CORS 콘솔 오류 부재를 검증한다.
- README, `kor-travel-geo-ui/README.md`, `docs/ports.md`, `docs/dev-environment.md`, `docs/agent-workflow.md`, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/decisions.md`, `docs/resume.md`, API reference 예시를 새 포트 원칙으로 갱신했다.

**검증**:
- ext4 테스트 미러에서 `bash -n scripts/docker_app.sh`, `scripts/docker_app.sh --help`, `kor-travel-geo-ui` `npm run type-check`, `npm run lint`, `npm run test`, `npm run build`를 통과했다. unit test는 11 files / 42 tests 통과다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- `scripts/docker_app.sh build`로 API/UI 이미지를 빌드했고, API build/runtime에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- `scripts/docker_app.sh up`으로 API `http://127.0.0.1:9001`, UI `http://127.0.0.1:9002`를 올렸다. `/v1/healthz`, `/debug/geocode`, `/api/runtime-config`가 200을 반환했고 VWorld 키는 길이만 확인했다.
- `/debug/geocode` 20회 반복 HTTP load에서 `This page couldn`와 `지도 타일 로딩이 불안정합니다` 문자열이 나오지 않았다.
- UI proxy `POST /api/proxy/v2/geocode` 실제 DB smoke가 `status=OK`, 후보 1건을 반환했다.
- Windows Firefox Playwright: `PLAYWRIGHT_BASE_URL=http://localhost:9002`, `PLAYWRIGHT_BROWSER=firefox`, `tests/e2e/vworld-map.spec.ts` → 2 passed.
- Python `ruff`는 ext4 미러에 Python dev venv가 없어 실행하지 못했다. 이번 Python 변경(`scripts/benchmark_api_latency.py`)은 기본 URL 문자열 변경이며 `python3 -m compileall -q scripts/benchmark_api_latency.py`는 통과했다.

## 2026-06-02 23:20 (PR #114~#115 리뷰 감사와 실제 DB 테스트 보강)

**작업**: PR #114부터 최신 PR #115까지 conversation comment, review body, inline review thread를 모두 확인하고, 사용자 지시에 맞춰 PR #114 기능의 실제 PostgreSQL 회귀 테스트를 추가했다.

**반영**:
- `docs/postmerge-review-fixups-pr114-pr115.md`에 PR별 리뷰 표면 확인 결과를 기록했다. 두 PR 모두 conversation comment 0건, review body 0건, review thread 0건이었다.
- `tests/integration/test_optional_real_postgres_regions.py`를 추가했다. `KTG_TEST_PG_DSN`이 설정된 실제 DB에서 `tl_scco_emd`의 `ST_PointOnSurface` 좌표를 사용해 `AsyncAddressClient.regions_within_radius()`가 `sido`/`sigungu`/`emd` contains 후보를 반환하는지 검증한다.
- `docs/resume.md`, `docs/tasks.md`에 이번 감사와 테스트 보강 상태를 반영했다.

**검증**:
- ext4 테스트 미러에서 `python -m pytest tests/integration/test_optional_real_postgres_regions.py -q` → `1 skipped`.
- `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo`로 T-027 최종 DB 대상 새 테스트 실행 → `1 passed`.
- `python -m ruff check .`, `python -m mypy src/kortravelgeo`, `lint-imports`, `python -m pytest -q` → 통과(`294 passed, 9 skipped`).

**발견**:
- PR #114와 PR #115는 GitHub의 세 리뷰 표면 모두에 남은 코멘트가 없었다.

## 2026-06-02 22:05 (세션 실행 실수 복기와 재발 방지 런북 보강)

**작업**: 이번 세션에서 반복된 CLI 접근, npm 서버 파라미터, WSL/Windows 실행 분리, 환경 설정, 서버 정리 실수를 복기해 문서화했다. 같은 명령을 여러 번 반복하지 않도록 실패 유형별 전환 규칙을 추가했다.

**반영**:
- `docs/agent-failure-patterns.md`에 `gh --repo` 사용, WSL Linux Node 초기화, npm script 인자 `--` 전달, Windows Playwright env var 전달, CodeGraph sync/status 순서, generated `next-env.d.ts` 복구, long-running server PID 종료, 반복 시도 제한 규칙을 추가했다.
- `docs/agent-workflow.md`에 WSL production UI 서버 실행, Windows Playwright 접속, VWorld runtime config 확인, 서버 종료, GitHub CLI, CodeGraph 표준 명령을 붙여넣기 가능한 형태로 추가했다.
- `docs/dev-environment.md`, `docs/resume.md`, `CHANGELOG.md`에 같은 운영 기준을 요약 반영했다.

**검증**:
- 문서-only 변경이다. `git.exe diff --check`로 whitespace를 확인한다.

**발견**:
- `gh`는 GitHub API 도구지만 로컬 repository context를 생략하면 WSL에서 Windows Git metadata를 읽으려 한다. PR 조회·머지에는 `--repo digitie/kor-travel-geo`를 붙이는 것이 안정적이다.
- Next.js 서버 인자는 npm script 구분자 `--` 뒤에 둬야 하며, 실제 지도 e2e는 WSL `next start --hostname 0.0.0.0` 서버에 Windows Playwright를 붙이는 방식이 가장 재현성이 높았다.

## 2026-06-02 21:10 (`/v2/regions/within-radius`와 VWorld 지도 실키 검증)

**작업**: `krtourmap` ADR-045 방향에 맞춰 POI 좌표 기준 반경 `n km` 안에 포함되는 시도·시군구·읍면동을 반환하는 v2 API와 Python client 함수를 추가하고, admin/debug UI에서 해당 함수를 직접 디버깅할 수 있게 했다. VWorld 지도 키는 Python API `.env`의 `KTG_VWORLD_API_KEY`를 우선 읽도록 바꿨고, 확보한 키로 실제 MapLibre/VWorld WMTS 로딩을 검증했다.

**반영**:
- `RegionsWithinRadiusInput`/`Response` DTO, `AsyncAddressClient.regions_within_radius()`, `POST /v2/regions/within-radius`, PostGIS raw SQL repository 함수를 추가했다.
- SQL은 입력 POI를 EPSG:5179로 한 번만 변환하고, `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`의 원본 geometry에 `ST_DWithin`/`ST_Covers`를 적용해 index 사용 방향을 유지했다.
- `/debug/geocode`에 `RegionsWithinRadiusDebugger`를 추가했다. 폼은 React Hook Form/Zod, 요청은 TanStack Query mutation, 마지막 초안/결과는 Zustand store, UI primitive는 shadcn/ui source component로 구성했다.
- `kor-travel-geo-ui` runtime config가 프로세스 환경 또는 저장소 루트 `.env`의 `KTG_VWORLD_API_KEY`를 먼저 읽고, 없을 때만 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용하도록 했다.
- `openapi.json`, frontend generated type/schema, v2 API reference, frontend/backend 문서, CHANGELOG, resume를 갱신했다. 프론트엔드 실행은 WSL Linux Node/npm, Playwright 실행과 브라우저는 Windows로 분리한다는 정책도 문서에 보강했다.
- MapLibre 자체는 `maplibre-vworld` package 경계를 유지하고, 별도 지도 fallback 구현을 만들지 않는다고 문서 경계를 정리했다.

**검증**:
- Backend ext4 mirror: `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `TMPDIR=/tmp TMP=/tmp TEMP=/tmp pytest -q` → `294 passed, 8 skipped`.
- Frontend ext4 mirror: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.
- React Doctor: `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- Windows Playwright: WSL production UI 서버(`next start --hostname 0.0.0.0 --port 13090`)를 대상으로 `PLAYWRIGHT_BASE_URL=http://<WSL_IP>:13090 npx playwright test --config playwright.config.ts --project chromium --workers 1` → `14 passed`.
- 실제 지도 테스트: `vworld-map.spec.ts`가 runtime config에서 Python `.env` VWorld 키가 비어 있지 않음을 확인하고, `/debug/geocode`의 MapLibre canvas와 `https://api.vworld.kr/req/wmts/1.0.0/` 타일 응답을 확인했다. 키 값 자체는 로그에 남기지 않았다.

**발견**:
- Windows `cmd.exe`에서 WSL 서버 대상 e2e를 실행할 때는 `cmd.exe /V:ON /C "set PLAYWRIGHT_BASE_URL=http://<WSL_IP>:<PORT>&& npx playwright test ..."` 형태가 안정적이었다.
- CodeGraph MCP 도구는 현재 세션에 노출되지 않아 CLI `codegraph sync/status/impact`로 UI 영향 범위를 임시 확인했다.

## 2026-06-01 19:52 (`/admin` 기본 라우트와 React Doctor 후속 규칙)

**작업**: `/admin/` 진입 시 404가 나오지 않도록 기본 admin 라우트를 추가하고, 모든 프론트엔드 작업 뒤 React Doctor를 실행해 경고를 수정·재실행하는 규칙을 문서화했다.

**반영**:
- `kor-travel-geo-ui/app/admin/page.tsx`를 추가해 `/admin` 기본 진입을 `/debug/geocode`로 redirect한다.
- `AGENTS.md`, `SKILL.md`, `docs/frontend-package.md`, `docs/resume.md`, `kor-travel-geo-ui/README.md`, `kor-travel-geo-ui/SKILL.md`에 React Doctor 실행·수정·재실행 규칙을 추가했다.
- 루트 `CHANGELOG.md`와 `kor-travel-geo-ui/CHANGELOG.md`에 사용자 가시 변경을 기록했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-admin-redirect`에서 `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0.
- 같은 mirror에서 `scripts/frontend_check.sh` → `gen:types`, `lint`, `type-check`, unit test 37개, `next build` 통과.
- `next start --port 13089` 후 `curl -i http://127.0.0.1:13089/admin` → `307 Temporary Redirect`, `location: /debug/geocode` 확인. `/admin/`은 Next.js canonical `308` 뒤 `/admin`으로 이동한다.

**발견**:
- 기존 공용 ext4 미러에는 root 소유 `node_modules/.vite`와 `.next` 생성물이 남아 있어 Vitest/Next build write가 막혔다. 검증은 새 mirror에서 `npm ci`부터 다시 실행해 통과시켰다.

## 2026-06-01 13:25 (반복 실패 패턴 원인 정리와 재발 방지 문서화)

**작업**: 이번 세션에서 반복된 에이전트 작업 실패 패턴을 원인별로 정리하고, 다음 세션이 같은 함정을 다시 밟지 않도록 운영 문서를 보강했다.

**반영**:
- `docs/agent-failure-patterns.md`를 추가해 NTFS worktree의 WSL `git` 실패, `exec_command`의 `CreateProcess ... os error 2`, NTFS 경로에서 `apply_patch` 실패, inline rewrite escape 손상을 각각 증상/원인/재발 방지/표준 대응으로 정리했다.
- `docs/agent-guide.md`, `docs/dev-environment.md`, `SKILL.md`에 새 문서 링크와 핵심 우회 원칙을 추가했다.
- `docs/resume.md`와 `CHANGELOG.md`에 이번 문서화 상태를 반영했다.

**발견**:
- NTFS worktree의 Git metadata는 정책상 Windows 경로를 유지하므로 WSL `git` 실패는 버그가 아니라 설계 결과다. 같은 증상이 보이면 즉시 Windows `git.exe -C F:/...`로 전환하는 것이 정답이다.
- `CreateProcess ... os error 2`는 저장소 파일 문제보다 Codex 명령 런처의 quoting/heredoc/workdir 처리 한계일 가능성이 높았다. 단순 명령(`sed`, `rg`, `cd ... && npm run ...`)은 안정적으로 재현됐다.
- NTFS 파일을 inline script로 편집할 때 `\n`, regex backslash, Windows path가 쉽게 손상돼, fallback edit 뒤 재열기와 lint/type-check가 필수다.

**다음**:
- 같은 패턴이 다시 보이면 먼저 `docs/agent-failure-patterns.md` 절차를 적용하고, 새 변종이면 이 문서에 추가한다.

## 2026-06-01 12:50 (React Doctor 잔여 경고 0건 마무리)

**작업**: admin 구조 분해 이후 남아 있던 debug/common React Doctor 경고를 모두 정리했다.

**반영**:
- `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`에서 prop JSX를 static fallback/skeleton으로 고정하고 click handler 이름을 구체화했다.
- `kor-travel-geo-ui/components/debug/GeocodeDebugger.tsx`는 `useReducer`로 state를 묶고, `NormalizeDebugger`는 `normalizeFormSchema`를 실제 입력 검증에 연결했다.
- `kor-travel-geo-ui/app/page.tsx`, `app/debug/*/page.tsx`에 page metadata를 추가했다.
- `kor-travel-geo-ui/lib/sido.ts`는 regex matcher + escape helper로 정리했고, `lib/schemas.ts`, `lib/consistency.ts`, `tests/unit/schemas.test.ts`를 정리해 dead-code 경고를 줄였다.
- `kor-travel-geo-ui/scripts/gen-types.mjs`는 `openapi-typescript` CLI 경로 호출 대신 Node API import 방식으로 정리했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 다시 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `96 → 100`, warning `15 → 0`이 됐다.

## 2026-06-01 10:55 (React Doctor admin 구조 분해 마무리)

**작업**: 남아 있던 admin React Doctor 구조 경고를 마저 정리하고, ext4 테스트 미러에서 전체 frontend 검증을 다시 수행했다.

**반영**:
- `kor-travel-geo-ui/components/admin/LoadConsole.tsx`를 workflow/controller + upload/review/jobs/dialog 섹션으로 분리하고 UI state를 `useReducer`로 묶었다.
- `kor-travel-geo-ui/components/admin/BackupsPanel.tsx`를 controller hook과 backup/restore/jobs/artifacts 패널로 나눠 giant component 경고를 제거했다.
- `kor-travel-geo-ui/components/admin/ConsistencyPanel.tsx`를 query/controller hook과 reports/workbench/layout 섹션으로 분리해 admin 쪽 마지막 `no-giant-component` 경고를 제거했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 다시 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `95 → 96`, warning `19 → 15`로 감소했고 admin 관련 경고는 0건이 됐다. 남은 항목은 debug page metadata, `CoordinateMap`, `GeocodeDebugger`, dead-code 계열이다.

## 2026-06-01 08:45 (React Doctor 기반 admin UI 정리)

**작업**: `react-doctor`를 다시 실행하고 admin UI 경고 중 동작/구조상 바로 고칠 수 있는 항목을 수정했다.

**반영**:
- `kor-travel-geo-ui/lib/vworld-key.tsx`를 TanStack Query 기반 runtime-config 로딩으로 바꿔 `fetch` in `useEffect`를 제거했다.
- `/admin/settings`는 prop 동기화 effect와 derived `useState`를 없애고 브라우저 override 입력 흐름을 draft 값으로 재구성했다.
- `/admin/consistency`는 invalid case 보정을 effect/setState 대신 렌더 시점 파생 선택으로 바꾸고, stale sample selection이 bulk action에 남지 않도록 정리했다.
- `/admin/load`는 병렬 업로드 + multi-XHR cancel, semantic `<dialog>`, lazy ref init, proxy `cache: "no-store"`로 정리했다.
- `/admin/ops`, `/admin/backups`는 관련 state를 묶어 `useState` 남용 경고를 줄였고, `tests/unit/vworld-key.test.tsx`는 QueryClientProvider fixture를 추가했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `90 → 95`, warning `59 → 19`로 감소했다. 남은 항목은 주로 giant component, debug page metadata, dead-code 계열 경고다.

## 2026-06-01 02:40 (T-027/T-047 국가지점번호 포함 재적재와 튜닝 재측정)

**작업**: 사용자 지시에 따라 새 Docker DB `kor-travel-geo-t027-retune`(port `15435`)에서 T-027 전체 적재를 다시 수행하고, 국가지점번호(`tl_sppn_makarea`)를 포함한 T-047 SQL benchmark를 재측정했다. 기존 T-027 최종 DB(port `15434`)는 보존했다.

**반영**:
- `scripts/benchmark_query_performance.py`가 Q11 `sppn_geocode`와 `sppn_reverse`를 모두 측정하도록 보강했다.
- `/v2/reverse` 변환 경로가 v1 `x_extension.sppn_makarea`를 `CandidateV2(match_kind="sppn")` 후보로 승격하도록 했다.
- `scripts/fullload_test.sh` smoke를 최신 v2 Python client 계약(`candidates`, `reverse()`)에 맞췄다.
- `docs/t027-t047-sppn-retune-20260601.md`에 full-load, 전체 daily 적용, 정합성 변화, benchmark 전후 차이, 데이터 보강 의견을 상세 기록했다.

**검증**:
- full-load: `tl_juso_text=6,416,642`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,416,642`까지 적재 완료. 초기 script는 구형 smoke 계약 때문에 exit 1이었지만 적재는 완료됐고, smoke script를 고친 뒤 수동 smoke를 통과했다.
- daily: 20260402~20260506 daily ZIP 35개를 추가 적용했다. 실제 daily 데이터가 충분해 synthetic delta는 만들지 않았다. 최종 `mv_geocode_target=6,418,735`, `mv_geocode_text_search=6,418,735`.
- consistency: 최종 report `consistency_770acd176f564141abadf95de0009773`, `severity_max=ERROR`. C1/C2/C3은 개선됐고 C4/C6/C7/C8은 기준월 혼합과 direct 출입구 변화 영향으로 증가했다.
- T-047: `t047-retune-standard-20260601-012814`, 2,000 case, 18,000 measurement, error 0. Q11 c64 p95는 `sppn_geocode=90.22ms`, `sppn_reverse=87.45ms`.
- unit smoke: `pytest tests/unit/test_query_performance_benchmark.py tests/unit/test_cli_contract.py tests/unit/test_v2_api.py tests/unit/test_sppn_core.py -q` → 37 passed.

## 2026-05-31 22:44 (VWorld 최신 wrapper 동기화와 PR #108 문서 기준 반영)

**작업**: 사용자 지시에 따라 로컬 git secret 파일에서 VWorld 키 존재 여부만 확인하고, PR #108의 당시 인프라 설정 파일 `./data/*` 기본 볼륨 기준이 현재 코드에 이미 반영되어 있음을 확인했다. `maplibre-vworld-js` upstream `main` 최신 commit `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`과 package version `0.1.2`를 확인한 뒤 `kor-travel-geo-ui` dependency/lockfile을 갱신했다.

**반영**:
- `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`를 직접 `maplibregl.Map` lifecycle 소유 방식에서 upstream `VWorldMap`/`Marker`/`useMap`/`useMapLoaded`를 감싸는 domain wrapper로 전환했다.
- `kor-travel-geo-ui/lib/vworld.ts`의 `getVWorldRasterStyle`, `redactVWorldTileUrl` local alias를 제거하고 upstream 이름인 `getVWorldStyle()`, `redactVWorldUrl()`로 호출자를 옮겼다.
- `README.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/external-apis.md`, `docs/frontend-package.md`, `docs/resume.md`, `kor-travel-geo-ui/README.md`, `kor-travel-geo-ui/CHANGELOG.md`에 최신 SHA, npm registry 미출시 상태, `VWorldMap` wrapper 전환을 반영했다.
- CodeGraph MCP는 현재 세션 도구로 노출되지 않아 CLI `codegraph sync/status/impact`로 `CoordinateMap.tsx` 영향도를 확인했다.

**검증**:
- ext4 테스트 미러: `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q` → 통과.
- Docker Node(ext4 mirror): `npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build` → 통과.
- T-027 최종 DB pgdata(`/home/digitie/kor-travel-geo-data/pgdata-final-20260529`)를 유지한 채 `kor-travel-geo-t027-final` DB 컨테이너를 재기동했고, API를 `0.0.0.0:8888`로 다시 띄웠다.
- 기존 UI 컨테이너를 내리고 `docker build --no-cache -t kor-travel-geo-ui:vworld-pr108 ./kor-travel-geo-ui`로 클린 빌드한 뒤 `kor-travel-geo-ui-vworld-pr108`을 `13088` 포트에 재기동했다.
- `/v1/healthz`, UI proxy `/api/proxy/v1/healthz`, `/debug/geocode`, `/api/runtime-config` VWorld key 주입, `/v2/geocode`, `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse` smoke를 확인했다.

## 2026-05-31 19:35 (Windows Git 기준과 T-027 DB 재사용 고정)

**작업**: 사용자 지시에 따라 WSL 테스트 미러에서 실행하더라도 Git metadata는 Windows Git과 Windows repo 경로를 기준으로 읽도록 정리했고, PostgreSQL 검증 DB는 새 클린 DB가 아니라 T-027 최종 적재 DB를 재사용하도록 복구했다.

**반영**:
- `scripts/benchmark_api_latency.py`, `scripts/benchmark_query_performance.py`, `scripts/capture_deployment_envelope.py`가 `KTG_GIT_REPO` 또는 ext4 미러 이름에서 `F:/dev/kor-travel-geo-*` 경로를 만들고 Windows `git.exe`로 branch/commit을 수집하도록 바꿨다.
- NTFS worktree의 `.git`/`gitdir` 포인터를 Windows Git 기준 `F:/dev/...`로 되돌렸다. WSL `git` 편의를 위해 `/mnt/f/...`로 바꾸지 않는 규칙을 문서화했다.
- `AGENTS.md`, README, `SKILL.md`, `docs/dev-environment.md`, `docs/agent-guide.md`, `docs/resume.md`에 Windows Git 기준과 T-027 DB 재사용 원칙을 추가했다.
- `kor-travel-geo-codex-clean` DB 컨테이너를 내리고, T-027 최종 pgdata(`/home/digitie/kor-travel-geo-data/pgdata-final-20260529`)를 쓰는 `kor-travel-geo-t027-final` DB를 port `15434`로 다시 올렸다.

**검증**:
- Windows Git: `git.exe -C F:/dev/kor-travel-geo-codex status --short --branch`가 `agent/codex-idle` worktree와 현재 변경 파일을 정상 표시했다.
- ext4 미러에서 세 스크립트의 Git helper가 모두 `agent/codex-idle`을 반환했다.
- T-027 DB row count: `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204`.
- `git.exe -C F:/dev/kor-travel-geo-codex diff --check` → 통과.

## 2026-05-31 14:10 (NTFS main repo와 에이전트 worktree 전환)

**작업**: 사용자 지시에 따라 Git source of truth를 NTFS main repo로 두고, 테스트는 WSL ext4 미러에서 수행하는 정책으로 전환했다.

**반영**:
- NTFS `/mnt/f/dev/kor-travel-geo`를 main repo 기준으로 두고 `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity` worktree를 생성했다.
- 각 worktree에 `.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json`, `backend/.env.local`, `web/.env.local`을 복사했다. secret 값은 출력하지 않았다.
- `kor-travel-geo-ui/.env.local`의 `KTG_API_INTERNAL_URL`은 공식 API 포트 `8888`에 맞춰 `http://localhost:8888`로 정리했다.
- 세 worktree에서 `codegraph init -i`와 `codegraph status`를 실행했다. NTFS `/mnt` 경로에서는 CodeGraph live watch가 비활성화되므로 이후 branch 전환·pull·merge 뒤 수동 `codegraph sync`가 필요하다.
- `.claude/`를 `.gitignore`에 추가하고, `AGENTS.md`, `SKILL.md`, README, 개발 환경/아키텍처/에이전트 가이드, ADR-041, resume, tasks를 갱신했다.

**검증**:
- `git worktree list`에서 `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity` 등록을 확인했다.
- 세 NTFS worktree의 `git status --short --branch`가 각각 `agent/*-idle...origin/main` clean 상태임을 확인했다.
- 세 NTFS worktree에서 `codegraph sync` → already up to date, `codegraph status` → 249 files, 4,042 nodes, 9,841 edges, `Index is up to date`를 확인했다.
- `rg`로 현재 운영 문서의 예전 ext4 source-of-truth 문구를 점검했다. 남은 `geo-*`/ext4 중심 문구는 superseded ADR-034와 과거 journal/검증 로그로 확인했다.
- `git diff --check` → 통과.

## 2026-05-31 11:40 (API 공식 포트 8888 전환)

**작업**: 사용자 지시에 따라 PC/WSL 개발 환경의 FastAPI 공식 host 포트를 `8000`에서 `8888`로 조정했다.

**반영**:
- README, `docs/ports.md`, `docs/dev-environment.md`, ADR-040의 공식 API 포트를 `8888`로 갱신했다.
- `KTG_API_INTERNAL_URL` 예시와 `kor-travel-geo-ui` 프록시 기본 backend URL을 `http://localhost:8888`로 바꿨다.
- API reference curl 예시와 REST latency benchmark 기본 `--base-url`도 `8888`로 맞췄다.

**검증**:
- `npm run type-check` → 통과
- `npm run test` → `36 passed`
- `npm run build` → 통과
- `python -m ruff check scripts/benchmark_api_latency.py` → 통과
- `git diff --check` → 통과
- `curl http://127.0.0.1:8888/v1/healthz` → `{"status":"ok"}`
- `curl http://127.0.0.1:13088/api/proxy/v1/healthz` → `{"status":"ok"}`

## 2026-05-31 08:15 (PR #97~#102 리뷰 감사, C1~C10 가로 탭, 포트 공식화)

**작업**: PR #97부터 최신 PR #102까지 상세 리뷰 표면을 확인하고, `/admin/consistency`의 C1~C10 case 선택 UX와 로컬 포트 정책을 정리했다.

**반영**:
- `gh pr view`와 GraphQL `reviewThreads`로 PR #97~#102를 확인했고 unresolved review thread는 전부 0건이었다. PR #98은 #97과 중복되어 close된 상태라 별도 반영 대상이 없었다. 상세 기록은 `docs/postmerge-review-fixups-pr97-pr102.md`에 남겼다.
- `/admin/consistency`의 세로 case rail을 `role=tablist` 기반 가로 스크롤 탭으로 바꿨다. C1~C10은 표본 분석 영역 위에서 좌우 스크롤로 선택하며, 선택 case는 `aria-selected`와 `tabpanel`로 연결된다.
- consistency unit/e2e mock을 C1~C10 전체로 확장하고, C10 탭 존재와 선택 탭 상태를 회귀 테스트로 고정했다.
- 공식 로컬 포트를 PostgreSQL `15434`, FastAPI `8000`, UI `13088`로 문서화했다. `.env.example`, 당시 인프라 설정 파일, README, `kor-travel-geo-ui/README.md`, `docs/ports.md`, `docs/dev-environment.md`, ADR-040을 갱신했다.
- Playwright e2e는 Windows Node/브라우저에서만 실행한다고 문서화했다. WSL에서는 반복적으로 `libasound.so.2` 누락이 발생하므로 `npm run test:e2e`를 실행하지 않는다.

**검증**:
- `npm run lint` → 통과
- `npm run type-check` → 통과
- `npm run test -- consistency-panel` → `3 passed`
- `npm run test` → `36 passed`
- `npm run build` → 통과
- `git diff --check` → 통과
- 공식 UI 포트 `13088` dev server에서 `/admin/consistency` HTML에 `case-tab-list`가 포함됨을 확인했다.
- WSL Playwright는 `libasound.so.2` 누락으로 실패했다. 이 경로는 더 이상 검증 루틴으로 쓰지 않는다.

## 2026-05-31 01:10 (에이전트별 MCP 설정 추가)

**작업**: Claude Code, GPT Codex, Antigravity 에이전트의 로컬 설정 파일에 `playwright` 및 `sequential-thinking` MCP 서버를 추가했다.

**반영**:
- `.codex/config.toml`에 `playwright` 및 `sequential-thinking` MCP 서버 구성을 TOML 형식으로 반영했다.
- `claude.json`과 `antigravity.json`을 새로 생성하여 해당 MCP 구성을 JSON 형식으로 반영했다.
- 생성/변경된 3가지 설정 파일을 git staging 영역에 등록했다.

## 2026-05-30 11:45 (T-067 v2 geocode point+geometry overlay)

**작업**: `/v2/geocode`와 디버그 UI에서 기존 대표점(`point`)을 유지하면서 행정구역/도로/건물 도형을 함께 확인할 수 있도록 보강했다.

**반영**:
- `GeocodeV2Input.include_geometry`와 `CandidateV2.geometry`/`GeometryV2`를 추가했다. 기본값은 `false`이며, 디버그 UI는 기본으로 `true`를 보낸다.
- 건물 주소는 기존 geocode 후보의 `point`를 그대로 유지하고 `tl_spbd_buld_polygon` polygon을 추가한다. `bd_mgt_sn` 직접 lookup이 실패하면 `rncode_full + bjd_cd + 건물번호` natural key로 도형을 찾는다.
- 상세번호 없는 도로명 입력은 district fallback 전에 `tl_sprd_manage` 도로 line 후보를 먼저 반환한다.
- 행정구역 후보는 `tl_scco_ctprvn/sig/emd/li` 도형을 후보에 붙인다.
- `/debug/geocode`와 `/debug/reverse`는 응답 JSON을 입력 아래에 두고, 지도 패널을 크게 분리했다. `CoordinateMap`은 point marker와 GeoJSON overlay를 동시에 표시하며, viewport는 `bbox`와 `point`를 함께 포함한다.

**실제 DB 확인**:
- `성복동` → `match_kind=region`, point `(127.05932949615165, 37.319558336433374)`, `geometry=region/MultiPolygon`
- `성복1로` → `match_kind=road`, point `(127.0610437873178, 37.32091740399021)`, `geometry=road/MultiLineString`
- `성복1로 35` → 기존 point `(127.07430262108355, 37.31347098160811)` 유지, `geometry=building/MultiPolygon`

**검증**:
- `pytest tests/unit/test_v2_api.py -q` → `10 passed`
- `ruff check ...` → 통과
- `mypy --strict src/kortravelgeo/dto/v2.py src/kortravelgeo/core/protocols.py src/kortravelgeo/core/v2.py src/kortravelgeo/infra/geometry_repo.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/v2.py` → 통과
- `npm run gen:types`, `npm run lint`, `npm run type-check`, `npm run test` → 통과

## 2026-05-30 10:10 (T-066 Consistency 탭 진입 프리즈 완화)

**작업**: `/admin/consistency` 진입 시 브라우저 탭이 멈추는 현상을 우선 확인하고, 초기 렌더에서 무거운 지도 컴포넌트가 자동 로드되지 않도록 수정했다.

**반영**:
- 백엔드 consistency list/detail/sample/summary API는 Docker DB 기준 모두 정상 응답함을 확인했다.
- 기존 UI는 sample을 고르기 전에도 첫 `point` 샘플을 자동으로 지도에 넣어 `LazyCoordinateMap`과 MapLibre/VWorld 타일 요청을 즉시 시작했다.
- `selectedSampleId`가 없으면 `selectedSample=null`로 유지하고, sample 선택 전에는 지도 대신 가벼운 placeholder를 표시한다.
- `tests/unit/consistency-panel.test.tsx`를 추가해 샘플 목록 로드만으로는 `LazyCoordinateMap`이 호출되지 않고, 사용자가 sample을 클릭한 뒤에만 지도 컴포넌트가 로드되는지 고정했다.

**검증**:
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test -- consistency-panel consistency` → `2 passed`, `4 tests`
- WSL Playwright headless Chromium은 `libasound.so.2` 누락으로 실행하지 못했다. 최종 브라우저 회귀는 사용자가 지정한 Windows Playwright 환경에서 확인한다.

## 2026-05-30 08:45 (T-065 내비게이션용DB 시군구용건물명 검색 반영)

**작업**: `내비게이션용DB_전체분/match_build_*.txt`의 `시군구용건물명`을 적재·정규화하고 검색 후보에 반영했다.

**반영**:
- 실제 202604 전국 파일에서 `시군구용건물명`이 20번째 컬럼(`row[19]`)임을 확인했다. non-empty row는 `773,407 / 10,721,310`, distinct 값은 `77,790`개였다.
- `tl_navi_buld_centroid`에 `sigungu_buld_nm`과 generated column `sigungu_buld_nm_nrm`을 추가하고, loader COPY/upsert 경로에 연결했다.
- `mv_geocode_target`과 `mv_geocode_text_search`가 `sigungu_buld_nm_nrm`을 포함하도록 확장했다.
- `/v2/search` exact preflight와 broad trigram fallback에서 `sigungu_buld_nm_nrm`을 점수화한다.
- 실제 검증 중 shadow swap 후 `ANALYZE` transaction이 기본 statement timeout에 걸려, `shadow_swap_mv()`의 후속 ANALYZE transaction에도 `SET LOCAL statement_timeout = 0`을 추가했다.
- 두 번째 검증에서는 release metadata 기록 중 `SELECT max(source_yyyymm) FROM tl_navi_buld_centroid`가 기본 statement timeout에 걸려, `record_mv_refresh_release()`에도 운영 작업용 `SET LOCAL statement_timeout = 0`을 추가했다.

**실제 DB 검증**:
- Docker DB `localhost:15434`에 새 컬럼을 적용하고 NAVI를 재적재했다. 결과는 `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`, 소요 `457초`.
- `mv_geocode_target`/`mv_geocode_text_search`를 새 컬럼 포함 상태로 재생성했다. 수동 `SET statement_timeout=0` 후 `ANALYZE`는 `12초`에 완료됐다.
- timeout 보강 뒤 release metadata 기록 경로를 직접 재호출해 active release `7b3455b6-e682-4d16-92f7-65fcad33e219` 생성을 확인했다.
- 변경 전 `NOT_FOUND`였던 `/v2/search` `엄마집`, `sig_cd=26110`은 부산광역시 중구 영주로 58 후보를 반환했다. 20회 API 측정 p50 `6.03ms`, p95 `7.42ms`.
- 변경 전 `NOT_FOUND`였던 `/v2/search` `P-101동`, `sig_cd=26110`은 부산광역시 중구 초량상로 13 등 후보 4건을 반환했다. 20회 API 측정 p50 `16.53ms`, p95 `20.12ms`.

**검증**:
- `pytest tests/unit/test_navi_loader.py tests/unit/test_infra_repo_sql.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_alembic_migrations.py -q` → `34 passed`
- `pytest tests/integration/test_real_juso_text_loaders.py::test_actual_navi_files_load_building_centroid_and_entrance_rows -q` → `1 passed`
- `ruff check ...` → 통과
- Docker UI proxy `/api/proxy/v2/search` `엄마집`, `sig_cd=26110` → `OK`

## 2026-05-30 02:20 (상위 주소 geocode 후보와 내비 검색 후속 문서화)

**작업**: 별도 geocode 경로를 만들지 않고, 상세번호 없는 상위 주소 입력을 기존 `/v2/geocode` 후보 흐름 안에서 처리하도록 보강했다.

**반영**:
- `/v2/geocode`에서 도로명/지번 parser가 번호 부재로 실패하면 같은 입력을 `search(type="district")` 후보로 승격한다.
- `district` 검색은 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li` polygon을 사용하고 대표점은 `ST_PointOnSurface`로 계산한다.
- 실제 Docker DB에서 `수지구` 입력의 첫 후보가 `용인시 수지구(sig_cd=41465)`와 대표점 `(127.08875165616607, 37.3327969096687)`를 반환함을 확인했다.
- 사용자 지시에 따라 `내비게이션용DB_전체분`의 `시군구용건물명` 컬럼을 후속 T-065 검색 보강으로 등록하고, 적재/정규화/검색 helper MV/성능 기록 요구사항을 문서화했다.

**검증**:
- `pytest tests/unit/test_infra_repo_sql.py tests/unit/test_v2_api.py -q` → `27 passed`
- `/v2/geocode` `{"road_address":"수지구"}` smoke `OK`
- `/v2/search` `{"query":"수지구","type":"district"}` smoke `OK`

## 2026-05-30 01:40 (외부 API fallback 인증키 오류 명시화)

**작업**: `fallback="api"` 요청에서 외부 API fallback이 실패할 때 인증키/설정 문제와 단순 미검색이 구분되도록 보강했다.

**반영**:
- 백엔드 fallback은 `KTG_VWORLD_API_KEY` 또는 `KTG_JUSO_API_KEY`를 사용한다. UI 지도용 `NEXT_PUBLIC_VWORLD_API_KEY`만 있으면 fallback 키로 보지 않는다.
- `fallback="api"`인데 provider 키가 하나도 없으면 `E0503` 설정 오류와 함께 필요한 환경변수 hint를 반환한다.
- VWorld `INVALID_KEY`, Juso `E0001`/KEY 오류는 `E0501` 외부 API 인증 오류로 명시해 반환한다.
- 로컬 `.env`에는 사용자 제공 VWorld 키를 `KTG_VWORLD_API_KEY`로 추가하고 권한을 `600`으로 조정했다. `.env`는 gitignore 대상이라 커밋하지 않는다.

**검증**:
- 키 없음 상태 `/v2/geocode fallback=api` → HTTP 500, `E0503`, `KTG_VWORLD_API_KEY` hint 확인
- 잘못된 VWorld 키 상태 `/v2/geocode fallback=api` → HTTP 502, `E0501`, `VWorld API authentication failed`, `INVALID_KEY` hint 확인
- 사용자 제공 키로 `ExternalGeocodeClient` live VWorld geocode `OK`
- `pytest tests/unit/test_external_api.py -q` → `6 passed`

## 2026-05-30 00:55 (단독 구 이름 도로명주소 조회 보정)

**작업**: `수지구 성복1로 35`처럼 시군구가 복합명(`용인시 수지구`)으로 저장되어 있지만 사용자가 단독 구 이름만 입력한 도로명주소 조회를 보정했다.

**반영**:
- 기본 도로명 exact lookup은 기존처럼 `sgg_nm = :sgg` 조건을 유지한다.
- 정확 조회가 실패하고 입력 시군구가 공백 없는 단독 `구` 이름일 때만 별도 suffix retry를 1회 수행한다.
- suffix retry는 선행 와일드카드 `LIKE`를 쓰지 않고, `rn_nrm`/건물번호 exact 조건으로 후보를 좁힌 뒤 `right(sgg_nm, char_length(:sgg_suffix))`를 적용한다.

**검증**:
- `수지구 성복1로 35`, `용인시 수지구 성복1로 35`, `경기도 용인시 수지구 성복1로 35`, `성복1로 35` 모두 실제 Docker DB에서 `OK` 확인
- fallback query `EXPLAIN (ANALYZE, BUFFERS)` → `idx_mv_rn_nrm_exact` index scan, execution time 약 0.49ms
- `ruff check src/kortravelgeo/infra/geocode_repo.py tests/unit/test_infra_repo_sql.py`
- `pytest tests/unit/test_infra_repo_sql.py tests/unit/test_core_geocoder.py -q` → `23 passed`

## 2026-05-30 00:15 (VWorld 인증키 런타임 설정 UI)

**작업**: VWorld 인증키를 `.env`에서 런타임으로 읽고, UI에서 저장·수정할 수 있도록 보강했다.

**반영**:
- `/api/runtime-config`가 서버 런타임의 `NEXT_PUBLIC_VWORLD_API_KEY`를 `no-store` JSON으로 반환한다.
- `VWorldKeyProvider`가 `.env` 기본값을 읽고, 브라우저 localStorage override가 있으면 그 값을 우선 적용한다.
- `/admin/settings`에서 인증키 입력, 저장, `.env` 기본값 복원을 지원한다.
- `CoordinateMap`은 기존 build-time `process.env` 직접 참조 대신 provider의 런타임 키를 사용한다.

**검증**:
- `npm run lint`
- `npm run type-check`
- `npm run test` → `33 passed`
- `npm run build`
- `docker build -t kor-travel-geo-ui:debug-v2 ./kor-travel-geo-ui`
- Docker UI `/api/runtime-config` → 사용자 제공 VWorld 키 반환 확인
- Docker UI `/api/proxy/v2/geocode` smoke `OK`
- Windows Playwright: `8 passed`

## 2026-05-29 23:20 (디버그 UI v2 REST 전환과 Windows Playwright e2e)

**작업**: 디버그 UI의 geocode/reverse 화면이 v2 REST API를 직접 사용하는지 재확인하고, v1 기반 호출을 v2 요청 body 중심으로 전환했다.

**반영**:
- `/debug/geocode`는 `/v2/geocode`에 `road_address` 또는 `jibun_address`, `fallback`, `limit`을 POST한다.
- `/debug/reverse`는 `/v2/reverse`에 `lon`, `lat`, `crs`, `include_region`, `include_zipcode`, `radius_m`을 POST한다.
- 프론트엔드 proxy와 `backendPath()`가 `/v1/*`와 `/v2/*`를 모두 보존하되, non-versioned path는 기존처럼 `/v1`로 보낸다.
- `kor-travel-geo-ui` Dockerfile을 추가하고, Docker 이미지 실행 runbook을 README에 보강했다.
- Playwright e2e 6개를 추가해 도로명/지번 geocode body, 빈 주소 차단, reverse 기본 body, reverse 입력 변경, 범위 밖 좌표 차단을 검증한다.

**검증**:
- `npm run lint`
- `npm run type-check`
- `npm run test` → `30 passed`
- Windows Playwright: `6 passed`
- `npm run build`
- `docker build -t kor-travel-geo-ui:debug-v2 ./kor-travel-geo-ui`
- Docker UI `http://127.0.0.1:13088`에서 `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse` POST smoke `OK`

**후속**:
- 실제 백엔드와 연결한 UI e2e는 Docker UI + Windows Playwright 조합을 기준으로 실행한다.

## 2026-05-29 21:37 (Python 라이브러리 API v2 단일화)

**작업**: 사용자 요청에 따라 Python 라이브러리 주소 조회 API에서 v1-style 공개 메서드를 제거하고 v2 후보 schema를 접미사 없는 기본 메서드로 승격했다.

**반영**:
- `AsyncAddressClient.geocode()`, `reverse()`, `search()`가 각각 `GeocodeV2Response`, `ReverseV2Response`, `SearchV2Response`를 반환한다.
- 공개 Python API에서 `geocode_v2()`, `reverse_v2()`, `search_v2()`, `reverse_geocode()`를 제거했다.
- REST `/v1/*` 라우터는 내부 `_geocode_v1`, `_reverse_geocode_v1`, `_search_v1` adapter를 호출해 vworld 호환 응답을 유지한다.
- REST `/v2/*` 라우터는 접미사 없는 Python 메서드를 호출한다.
- ADR-039, README, API reference, backend/reverse/external API 문서를 갱신했다.

**검증 예정**:
- v2/client 단위 테스트, v1/v2 라우터 contract 테스트, ruff/mypy/lint-imports를 실행한다.

**후속**:
- 기존 Python 사용자가 vworld 호환 DTO를 직접 기대하는 경우 REST `/v1/*` 또는 별도 migration 문서를 안내한다.

## 2026-05-29 18:45 (PR #69~#86 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 T-027 PR merge 뒤 PR #69부터 최신 PR #86까지 conversation/review/latestReview/reviewThreads를 다시 확인했다.

**반영**:
- PR #69~#86 모두 merged 상태, conversation comment 0건, GraphQL review thread 0건임을 확인했다.
- PR #84 사후 리뷰를 반영해 GeoIP gate가 admission control보다 바깥에서 먼저 실행되도록 middleware 설치 순서를 바꿨다.
- `classify_ip()`의 `testclient` 호스트명 특별 허용을 제거해 잘못된 client host는 `invalid_client_ip`로 deny되게 했다.
- `X-Forwarded-For` 항목이 `1.2.3.4:port` 또는 `[IPv6]:port` 형태여도 마지막 untrusted client IP를 추출하도록 보강했다.
- `docs/postmerge-review-fixups-pr69-pr86.md`와 `docs/t054-korea-only-geoip.md`에 반영/보류 항목을 정리했다.

**검증**:
- `ruff check src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py tests/unit/test_geoip_gate.py`
- `pytest tests/unit/test_geoip_gate.py tests/unit/test_api_admission_control.py tests/unit/test_api_app_contract.py -q` → `14 passed`
- `mypy --no-incremental src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py`

**후속**:
- v2 `distance_m`/confidence/precision, C1~C10 전수 export, callback receiver 예제, release ledger repair, table 단위 shared lock은 후속 후보로 유지한다.

## 2026-05-29 18:05 (T-027 최종 실 데이터 클린 재적재 검증)

**작업**: 남은 튜닝/증분/보조 로더 작업을 모두 반영한 최신 코드로 실제 전국 데이터를 빈 Docker PostGIS DB에 처음부터 다시 적재했다.

**반영**:
- `scripts/fullload_test.sh`에 선택 `DAILY_JUSO_ZIP`/`DAILY_YYYYMM` phase를 추가해 full snapshot 뒤 실제 daily MST/LNBR delta를 함께 검증할 수 있게 했다.
- 새 compose project `kor-travel-geo-t027-final`, port `15434`, 전용 `pgdata-final-20260529`로 기존 DB와 분리해 클린 로드를 실행했다.
- 전체 3,963초, `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204`, active serving release `faa1f42b-f5b9-4ef0-af0b-1a422d938ed3`를 확인했다.
- `20260401_dailyjusukrdata.zip`은 `daily-juso` 422건 처리/upsert 242/delete 180, `daily-parcel-links` 204건 처리/upsert 74/delete 82로 적용됐다.
- C1~C10은 `severity_max=ERROR`이며 C2/C4/C6/C7은 기존 실제 원천 품질 이슈로 남았다. C2/C4/C6/C7 data-quality CSV 8개와 DB size snapshot을 남겼다.

**검증**:
- `PLAN_ONLY=1` preflight 통과
- `bash scripts/fullload_test.sh` → exit status 0, wall clock 1:06:02
- `ktgctl validate consistency --scope full` → `consistency_163e89acfb4a41e0a8c19599c2faa678`
- smoke: geocode/reverse/search/zipcode `OK`
- `ktgctl validate data-quality-samples --cases C2,C4,C6,C7 --limit 20` → CSV 8개 생성

**후속**:
- 즉시 실행 가능한 대기 task는 없다.
- N150/Odroid 실제 장비가 준비되면 T-063 실측을 진행한다.

## 2026-05-29 16:20 (T-055 N150/Odroid 운영 환경 비교 준비)

**작업**: 실제 N150/Odroid 장비 도착 전 수행 가능한 측정 준비를 완료했다.

**반영**:
- `scripts/capture_deployment_envelope.py`를 추가해 OS/CPU/메모리/NVMe/Docker/GDAL/PostgreSQL/fio/sysbench/zstd 정보를 `system-envelope.json`과 `system-envelope.md`로 캡처한다.
- 기본 실행은 부하가 낮은 시스템 정보만 수집하고, `fio`/`sysbench`는 `--run-probes`를 명시한 경우에만 실행하게 했다.
- T-027 full-load, T-047 SQL benchmark, REST e2e benchmark, MV refresh/swap benchmark를 같은 `artifacts/perf/n150-vs-odroid-*` 구조로 남기는 runbook을 `docs/t055-deployment-n150-odroid.md`에 고정했다.
- 실제 장비 실측은 하드웨어가 있어야 의미가 있으므로 T-063으로 보류하고, 다음 실행 가능 작업을 T-027 최종 클린 적재 검증으로 정리했다.

**검증**:
- `ruff check scripts/capture_deployment_envelope.py tests/unit/test_capture_deployment_envelope.py`
- `pytest tests/unit/test_capture_deployment_envelope.py -q` → `5 passed`
- `python scripts/capture_deployment_envelope.py --env-label wsl-smoke --data-dir data --output-dir /tmp/kortravel-t055-envelope-smoke`
- `ruff check .`
- `pytest -q` → `273 passed, 8 skipped`
- `mypy --no-incremental src/kortravelgeo`
- `lint-imports`

**후속**:
- PR merge 후 T-027 최종 실 데이터 클린 적재 검증으로 이어간다.
- N150/Odroid 장비가 준비되면 T-063에서 T-055 runbook으로 최소 3회 반복 실측한다.

## 2026-05-29 15:35 (T-054 한국 IP GeoIP gate)

**작업**: 외부 공용 IP에서 호출되는 REST API를 대한민국 IP로 제한하는 1차 middleware를 구현했다.

**반영**:
- `infra.geoip`에 IP/CIDR 분류, MaxMind country reader, trusted proxy `X-Forwarded-For` 처리, open path 판정을 추가했다.
- FastAPI middleware가 `/v1/healthz`, `/metrics`를 제외한 REST 표면에서 내부/loopback은 허용하고 공용 IP는 country `KR`만 허용한다.
- strict/permissive/off mode, allow/deny CIDR, trusted proxy, audit 설정을 `Settings`와 `.env.example`에 추가했다.
- deny 응답은 `E0403/403`이며, `geoip.denied` audit event에는 IP 원문을 payload에 넣지 않고 `AdminRepository`의 hash 경로를 사용한다.
- `ktgctl geoip check <ip>` 진단 명령과 단위/middleware 테스트를 추가했다.

**검증**:
- `ruff check src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py src/kortravelgeo/api/app.py src/kortravelgeo/cli/main.py src/kortravelgeo/settings.py tests/unit/test_geoip_gate.py tests/unit/test_settings.py`
- `pytest tests/unit/test_geoip_gate.py tests/unit/test_settings.py tests/unit/test_api_app_contract.py -q` → `14 passed`
- `mypy --no-incremental src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py src/kortravelgeo/api/app.py src/kortravelgeo/cli/main.py src/kortravelgeo/settings.py`
- CLI smoke: `ktgctl geoip check 8.8.8.8` → `geoip_db_unavailable` deny
- `ruff check .`, `pytest -q` → `268 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-055 N150/Odroid 실측 준비로 이어간다.

## 2026-05-29 14:45 (PR #69~#82 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #82 merge 뒤 PR #69부터 최신 PR #82까지 formal review와 review thread를 다시 확인했다.

**반영**:
- 모든 대상 PR의 GraphQL `reviewThreads.totalCount`는 0이었다.
- PR #81 리뷰에서 발견된 실제 런타임 버그를 수정했다. `replace_current` restore의 `maintenance_window.authorize` audit event가 `ops.audit_events.actor_type` CHECK에 없는 `job`을 쓰지 않도록 `system`으로 바꿨다.
- table stats scheduler 호출부에 `skip_if_locked=True`를 명시해 scheduler는 lock 충돌 시 조용히 skip하고, 수동 capture만 `409 E0409`로 실패한다는 의도를 고정했다.
- 상세 리뷰별 반영/보류 표는 `docs/postmerge-review-fixups-pr69-pr82.md`에 정리했다.

**검증**:
- `ruff check src/kortravelgeo/infra/backup.py src/kortravelgeo/api/app.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q` → `22 passed`
- `mypy --no-incremental src/kortravelgeo/infra/backup.py src/kortravelgeo/api/app.py`
- `ruff check .`, `pytest -q` → `261 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-054 한국 IP 외부 접근 차단으로 이어간다.

## 2026-05-29 13:45 (T-059 CLI/Job 동시 실행 보호 표준화)

**작업**: PostgreSQL advisory lock 기반 cross-process 실행 보호를 CLI와 API job handler에 표준 적용했다.

**반영**:
- `src/kortravelgeo/infra/concurrency.py`를 추가해 `AdvisoryLockNamespace`, `AdvisoryLockKey`, `ConcurrentExecutionError(E0409/409)`, `cross_process_lock()`을 제공한다.
- 주요 CLI 운영 명령(`init-db`, `load *`, `refresh mv`, `validate consistency`, `uploads cleanup`, `backup create`, `restore create`)이 명령별/path별/target별 lock key를 잡고 중복 실행 시 exit code 2로 fail-fast한다.
- FastAPI `JobQueue` 기본 handler도 같은 lock key를 잡도록 등록해 CLI와 API job이 같은 자원을 동시에 만지는 것을 막는다.
- PR #82 리뷰 후속으로 미사용 `wait` 경로와 혼동 가능한 `OPS_TABLE_STATS` enum 멤버를 제거하고, API queue의 lock 충돌은 `lock_conflict` progress event 후 `failed`로 닫는다고 문서화했다.
- 실제 Docker PostgreSQL에서 같은 `MV_REFRESH` key를 두 connection으로 잡아 두 번째 connection이 `E0409/409`로 막히는 smoke를 확인했다.
- CLI 단독 실행을 `load_jobs` row로 노출하는 운영 가시화는 후속으로 남겼다.

**검증**:
- `ruff check src/kortravelgeo/infra/concurrency.py src/kortravelgeo/cli/main.py src/kortravelgeo/api/app.py tests/unit/test_concurrency.py tests/unit/test_api_app_contract.py`
- `pytest tests/unit/test_api_app_contract.py tests/unit/test_concurrency.py -q` → `6 passed`
- `pytest tests/unit/test_concurrency.py tests/unit/test_client_submit_load_batch.py tests/unit/test_backup_restore.py -q` → `23 passed`
- Docker PostgreSQL smoke: 같은 `MV_REFRESH` key의 두 번째 connection이 `E0409/409`로 차단됨
- `ruff check .`, `pytest -q` → `261 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-054 한국 IP 외부 접근 차단으로 이어간다.

## 2026-05-29 12:35 (PR #69~#80 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 현재 작업 PR #80 merge 뒤 PR #69부터 최신 PR #80까지 상세 리뷰와 review thread를 다시 확인했다.

**반영**:
- PR #69~#75는 기존 `docs/postmerge-review-fixups-pr69-pr75.md`와 PR #76 반영 상태를 재확인했다.
- 모든 대상 PR의 GraphQL `reviewThreads.totalCount`는 0이었다.
- PR #77 후속으로 수동 table stats capture가 scheduler lock 충돌을 `[]` 성공처럼 반환하지 않고 `409 E0409`로 보고하도록 했다. scheduler만 기존처럼 `skip_if_locked=True`로 조용히 건너뛴다.
- PR #78 후속으로 `replace_current` restore가 active maintenance window를 통과할 때 `ops.audit_events(action='maintenance_window.authorize')`를 남기게 했다. window는 기간 gate로 유지하며 자동 소비하지 않는다고 문서화했다.
- PR #79와 #80은 머지 전 반영된 리뷰 후속이 main에 포함됐음을 재확인했다.

**검증**:
- `ruff check src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q` → `22 passed`
- `mypy --no-incremental src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py`
- `ruff check .`, `pytest -q` → `257 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-059 CLI/Job 동시 실행 보호 표준화로 이어간다.

## 2026-05-29 11:40 (PR #80 리뷰 후속 — restore hot-swap plan 보강)

**작업**: PR #80 formal review에서 나온 restore hot-swap plan의 edge case를 반영했다.

**반영**:
- 자동 `previous_alias` 생성 시 `datetime.now(UTC)`를 한 번만 고정해 DB 존재 확인과 반환 plan이 같은 alias를 보도록 했다.
- `existing_databases=None`은 미확인, 빈 set은 실제 확인 결과 0건으로 구분해 missing DB blocker를 보고한다.
- 현재 DB 이름이 긴 경우 `_previous_YYYYMMDD_HHMMSS` suffix를 보존하고 prefix를 잘라 PostgreSQL 63자 identifier 제한을 지킨다.
- managed/hardened cluster에서 `postgres` DB 접속이 제한될 수 있으므로 `maintenance_database`를 API/CLI 요청으로 지정할 수 있게 했다.

**검증**:
- `scripts/export_openapi.py`, `kor-travel-geo-ui npm run gen:types`
- `ruff check src/kortravelgeo/dto/admin.py src/kortravelgeo/infra/hotswap.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/admin.py src/kortravelgeo/cli/main.py tests/unit/test_restore_hotswap.py`
- `pytest tests/unit/test_restore_hotswap.py tests/unit/test_dto_search_zipcode_pobox_admin.py tests/unit/test_openapi_export.py -q` → `13 passed`
- `mypy --no-incremental src/kortravelgeo/infra/hotswap.py src/kortravelgeo/dto/admin.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/admin.py src/kortravelgeo/cli/main.py`
- CLI smoke: `ktgctl serving hot-swap-plan --restore-db kor_travel_geo_restore_missing --maintenance-db postgres`
- `ruff check .`, `pytest -q` → `257 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`
- `kor-travel-geo-ui` Linux npm gate: `lint`, `type-check`, `test`, `build`

**후속**:
- PR #80 CI 완료 후 5분 대기, 리뷰 재확인, merge를 진행한다.

## 2026-05-29 11:05 (T-058 restore hot-swap plan/preflight)

**작업**: T-058의 restore hot-swap 패턴을 실제 rename 실행 전 plan/preflight 표면으로 구현했다.

**반영**:
- `RestoreHotSwapPlanRequest`/`RestoreHotSwapPlan` DTO를 추가했다.
- `infra/hotswap.py`에서 current DB, restore DB, previous alias, maintenance DB, typed confirmation, rollback confirmation, blocker, SQL/steps를 산출한다.
- `/v1/admin/restores/hot-swap-plan` API와 `AsyncAddressClient.restore_hot_swap_plan()`을 추가했다.
- `ktgctl serving hot-swap-plan` CLI를 추가했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입을 갱신했다.
- 실제 `ALTER DATABASE ... RENAME` 실행은 ops metadata 위치와 worker별 engine refresh/rollback round-trip 검증이 더 필요해 후속 실행 표면으로 분리하고, T-058 문서에 명시했다.

**검증 예정**:
- hot-swap plan 단위 테스트, DTO/API/OpenAPI drift, backend/frontend gate를 실행한 뒤 PR을 올린다.

**후속**:
- 이 PR merge 후 T-059 CLI/Job 동시 실행 보호 표준화로 이어간다.

## 2026-05-29 09:45 (T-050 운영 hardening 7차 — 실제 PostgreSQL 제약 통합 테스트)

**작업**: T-050 마지막 항목인 실제 PostgreSQL FK/trigger/partial unique integration test를 추가했다.

**반영**:
- `tests/integration/test_optional_real_postgres_ops_constraints.py`를 추가했다.
- `KTG_TEST_PG_DSN`이 없으면 skip하고, 설정되면 `SCHEMA_SQL`/`INDEX_SQL`을 실제 DB에 적용한 뒤 운영 메타데이터 제약을 검증한다.
- `ops.audit_events.job_id` FK가 감사 이벤트가 붙은 `load_jobs` 삭제를 막는지 확인한다.
- `ops.audit_events` append-only trigger가 `UPDATE`와 `DELETE`를 모두 막는지 확인한다.
- `ops.serving_releases` active partial unique index가 active release 1건만 허용하고 pending release는 허용하는지 확인한다.
- `ops.table_stats_snapshots.snapshot_id` FK가 잘못된 dataset snapshot 참조를 막고 유효한 참조는 허용하는지 확인한다.
- PR #79 리뷰 Low 제안에 따라 DSN 대상 DB 이름 guard와 필수 extension package 사전 skip을 추가했다.
- T-050/resume/tasks/CHANGELOG 문서를 T-050 완료 상태로 갱신했다.

**검증**:
- `ruff check tests/integration/test_optional_real_postgres_ops_constraints.py`
- DSN 미설정: `pytest tests/integration/test_optional_real_postgres_ops_constraints.py -q` → `1 skipped`
- 실제 Docker PostgreSQL 별도 DB `kor_travel_geo_t050_ops_constraints`: `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t050_ops_constraints pytest tests/integration/test_optional_real_postgres_ops_constraints.py -q` → `1 passed`
- 테스트 완료 후 별도 DB를 삭제했다.

**후속**:
- 이 PR merge 후 T-058 restore hot-swap으로 이어간다.

## 2026-05-29 09:15 (T-050 운영 hardening 6차 — destructive confirmation flow)

**작업**: T-050 남은 항목 중 destructive confirmation flow를 기존 `db_restore` 위험 경로에 연결했다.

**반영**:
- `AdminRepository.require_active_maintenance_window()`를 추가해 active window, 유효 기간, confirmation hash를 함께 확인한다.
- `db_restore`의 `replace_current` 모드는 `target_dsn`을 받지 않고 target DB 이름이 현재 설정 DB 이름과 같아야 하며, 확인 문구 `RESTORE <현재 DB 이름>`이 일치해야 하고, 같은 확인 문구 hash를 가진 active `restore` maintenance window가 있어야 한다.
- 잘못된 target DB로 `replace_current`를 지정해 빈 DB preflight를 우회하는 경로를 차단했다.
- T-046/T-050/T-058/backend/frontend/resume/tasks/CHANGELOG 문서를 갱신했다.

**검증 예정**:
- backup/restore 단위 테스트와 ops metadata source contract를 실행한 뒤 전체 backend gate를 확인한다.

**후속**:
- 이 PR merge 후 실제 PostgreSQL FK/trigger/partial unique integration test로 T-050을 마무리한다.

## 2026-05-29 08:25 (T-050 운영 hardening 5차 — table stats 주기 capture)

**작업**: T-050 남은 항목 중 `ops.table_stats_snapshots` 주기 capture를 구현했다.

**반영**:
- `KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES`, `KTG_OPS_TABLE_STATS_CAPTURE_LIMIT`, `KTG_OPS_TABLE_STATS_CAPTURE_ON_STARTUP` 설정을 추가했다.
- FastAPI lifespan에서 interval이 1 이상일 때만 background task를 띄워 `AdminRepository.capture_table_stats_snapshots()`를 주기 실행한다.
- 여러 API worker의 동시 capture 중복을 줄이기 위해 `pg_try_advisory_xact_lock(0x4B4700A0)`을 capture transaction 앞에 추가했다.
- 수동/주기 capture에서 `snapshot_id`를 생략하면 현재 active serving release의 `snapshot_id`에 자동 연결한다.
- 연결 방식은 각 row의 `stats.snapshot_link`에 `explicit`, `active_serving_release`, `unlinked`로 남긴다.
- T-050/T-049/backend/frontend/data-model/resume/tasks/CHANGELOG 문서를 갱신했다.

**검증 예정**:
- backend targeted gate와 전체 backend gate를 실행한 뒤 PR을 열어 CI 완료 후 5분 대기/리뷰 확인/머지한다.

**후속**:
- 이 PR merge 후 T-050 destructive confirmation flow 통합으로 이어간다.

## 2026-05-29 07:20 (PR #69~#75 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #69부터 최신 PR #75까지 conversation/review/latestReview/reviewThreads를 재확인하고, formal review에서 바로 반영 가능한 항목을 코드와 문서로 보강했다.

**반영**:
- `kor-travel-geo-ui/package-lock.json`의 `maplibre-vworld` resolved URL을 `git+https`로 맞췄다.
- `AsyncAddressClient.list_consistency_case_samples()`가 표본 결과가 있을 때는 report 존재 확인 쿼리를 추가 실행하지 않도록 줄였다.
- `SizeProgressProbe`가 directory size sample을 interval 안에서 캐시해 backup/restore hot path의 반복 `rglob/stat` 부하를 줄였다.
- `mv_refresh`의 load-batch ERROR gate를 swap 이전으로 옮기고, release hook의 post-swap gate raise와 `mv_geocode_target` 중복 count를 제거했다.
- T-053 표본/전수 범위, callback retry 멱등성, helper MV raw refresh 금지, T-055 helper sizing, T-050 release ledger transaction 경계를 문서화했다.
- 상세 리뷰별 반영/보류 표는 `docs/postmerge-review-fixups-pr69-pr75.md`에 정리했다.

**검증 예정**:
- backend 전체 gate와 frontend gate를 실행한 뒤 PR을 열어 CI 완료 후 5분 대기/리뷰 확인/머지한다.

**후속**:
- 이 PR merge 후 T-050 `ops.table_stats_snapshots` 주기 capture로 이어간다.

## 2026-05-29 06:27 (T-050 운영 hardening 4차 — snapshot/release hook)

**작업**: full-load/MV refresh/restore 성공 지점을 `ops.dataset_snapshots`와 `ops.serving_releases`에 자동 연결하는 hook을 추가했다.

**반영**:
- `mv_refresh` 성공 후 active serving release와 released dataset snapshot을 기록한다.
- full-load batch에서 온 refresh는 root `source_set`과 최신 consistency gate를 연결하고, 단독 refresh는 `manual_rebuild` release로 기록한다.
- 새 active release 생성 전 기존 active release는 `superseded`로 전환한다.
- restore 성공 후에는 hot-swap 전 단계의 `validated` snapshot과 `pending` restore release 후보를 만들고 restore artifact manifest에 `snapshot_id`/`release_id`를 연결한다.
- `docs/t050-ops-hardening.md`, backend/frontend 문서, resume/tasks/CHANGELOG를 갱신했다.
- 사용자 최신 지시에 따라 이 PR merge 후 다음 작업은 PR #69부터 최신 PR까지 review audit/fixup을 먼저 진행한다.

**검증**:
- 대상 `ruff check src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/api/app.py src/kortravelgeo/infra/backup.py src/kortravelgeo/cli/main.py tests/unit/test_ops_metadata.py`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/api/app.py src/kortravelgeo/infra/backup.py src/kortravelgeo/cli/main.py`
- 대상 `pytest tests/unit/test_backup_restore.py tests/unit/test_ops_metadata.py tests/unit/test_infra_repo_sql.py -q`
- `lint-imports`

**후속**:
- T-050 4차 PR merge 후 PR #69부터 최신 PR까지 review audit/fixup을 진행한다.
- 이후 `ops.table_stats_snapshots` 주기 capture로 이어간다.

## 2026-05-29 05:17 (T-050 운영 hardening 3차 — backup/restore sub-progress)

**작업**: backup/restore의 대용량 단계가 멈춘 것처럼 보이지 않도록 file/archive size 기반 sub-progress를 추가했다.

**반영**:
- `SizeProgressProbe`와 byte formatter를 추가해 진행 중인 파일 또는 디렉터리 크기를 주기적으로 샘플링한다.
- `pg_dump` 실행 중 dump 디렉터리 크기를 `log_tail`에 남기고, dump checksum 생성 구간을 `0.65~0.70` progress로 분리했다.
- `tar.zst` archive 생성 전에 입력 크기를 계산하고, `.part` archive 파일 성장량을 보조 진행률로 기록한다.
- archive SHA256 계산 중 읽은 byte/전체 byte를 기록한다.
- restore extract 구간에서 extract 디렉터리 성장량을 archive 크기와 함께 기록하고, `pg_restore` 시작 메시지에는 dump 디렉터리 총량을 포함한다.
- `docs/t050-ops-hardening.md`, `docs/t046-db-backup-restore.md`, resume/tasks/CHANGELOG를 갱신했다.

**검증**:
- 대상 `ruff check src/kortravelgeo/infra/backup.py tests/unit/test_backup_restore.py`
- 대상 `pytest tests/unit/test_backup_restore.py -q`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/backup.py`

**후속**:
- PR merge 후 T-050 4차로 full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성을 진행한다.

## 2026-05-29 04:29 (T-050 운영 hardening 2차 — backup/restore callback)

**작업**: T-046 backup/restore callback을 1회 단순 전송에서 HMAC 서명, retry/backoff, replay 판별 가능한 전송 계약으로 보강했다.

**반영**:
- `KTG_BACKUP_CALLBACK_MAX_ATTEMPTS`, `KTG_BACKUP_CALLBACK_BACKOFF_MS`, `KTG_BACKUP_CALLBACK_SECRET` 설정을 추가했다.
- callback payload는 `callback_id`, `timestamp`, `attempt`, `max_attempts`를 포함하고, compact JSON byte를 기준으로 HMAC-SHA256 서명한다.
- header는 `x-kor-travel-geo-event`, `x-kor-travel-geo-callback-id`, `x-kor-travel-geo-timestamp`, `x-kor-travel-geo-signature`를 보낸다.
- 각 retry attempt마다 새 `callback_id`를 발급하고, delivery 결과를 `ops.artifacts.callback_state`와 `manifest.callback_delivery`에 기록한다.
- callback 실패는 backup/restore artifact 자체의 성공/실패를 뒤집지 않는다.
- `docs/t050-ops-hardening.md`와 `docs/t046-db-backup-restore.md`에 실제 payload/header/운영 기록 방식을 갱신했다.

**검증**:
- 대상 `ruff check`
- 대상 `pytest tests/unit/test_backup_restore.py tests/unit/test_settings.py -q`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/backup.py src/kortravelgeo/settings.py`

**후속**:
- PR merge 후 T-050 3차로 backup/restore file/archive size 기반 sub-progress를 진행한다.

## 2026-05-29 03:35 (T-050 운영 hardening 1차 — upload set cleanup)

**작업**: T-050을 여러 PR로 나누기로 하고, 첫 단위로 upload set cleanup TTL과 실행 중 job 참조 보호를 구현했다.

**반영**:
- `kortravelgeo.infra.uploads.cleanup_upload_sets()`를 추가했다. `loader_data_dir/uploads/upload_*`를 스캔하고 TTL이 지난 upload set을 삭제한다.
- `load_jobs.state IN ('queued','running')` payload에서 `upload_set_id` 또는 upload set 경로가 발견되면 삭제하지 않는다.
- manifest가 깨졌거나 없는 `upload_*` 디렉터리는 orphan으로 보되 TTL과 active grace가 모두 지난 경우에만 삭제한다.
- `AsyncAddressClient.cleanup_upload_sets()`와 `ktgctl uploads cleanup` CLI를 추가했다.
- 기본 설정 `KTG_UPLOAD_SET_TTL_DAYS=30`, `KTG_UPLOAD_SET_ACTIVE_GRACE_MINUTES=360`을 추가했다.
- `docs/t050-ops-hardening.md`에 T-050 전체 분할 순서와 1차 cleanup 운영 규칙을 정리했다.

**검증 예정**:
- `tests/unit/test_source_set_plan.py`, `tests/unit/test_settings.py`, `tests/unit/test_infra_repo_sql.py` targeted test 후 전체 backend gate를 실행한다.

**후속**:
- PR merge 후 T-050 2차로 backup/restore callback HMAC, retry/backoff, replay protection을 진행한다.

## 2026-05-29 02:30 (T-061 Q3 fuzzy slim text-search 구조)

**작업**: `mv_geocode_target`에서 재생성 가능한 read-only helper MV `mv_geocode_text_search`를 추가하고, Q3 fuzzy geocode와 Q4 broad search fallback 후보 추출에 연결했다.

**반영**:
- `alembic/versions/0013_t061_text_search_mv.py`와 `TEXT_SEARCH_MV_SQL`을 추가했다.
- `GeocodeRepository.fuzzy_roads()`는 helper MV에서 candidate를 먼저 뽑고 `bd_mgt_sn`으로 `mv_geocode_target`에 join한다.
- `SearchRepository.search()`는 Q4 exact preflight를 기존 target index 경로로 유지하고, exact가 없을 때 broad fallback만 helper MV를 사용한다.
- shadow swap은 `mv_geocode_target_next`와 `mv_geocode_text_search_next`를 함께 만들고 같은 rename window에서 교체한다.
- backup materialized-view 제외 옵션은 `mv_geocode_target`과 `mv_geocode_text_search` data를 함께 제외한다.
- `scripts/benchmark_query_performance.py`와 `scripts/benchmark_mv_refresh.py`가 helper MV row/size와 refresh/swap cost를 기록하도록 보강했다.

**실측**:
- T-057 corpus 기준 Q3 fuzzy c64 p95는 359.25ms → 227.57ms, `sig_cd` hint는 193.36ms → 182.27ms, wide는 255.36ms → 200.69ms.
- helper MV는 6,416,637행, heap 854MiB, index 1,572MiB, total 2,426MiB.
- helper-only rebuild는 채택 DDL 기준 82.77초.
- helper 포함 shadow swap은 497.54초, helper text-search build/index phase는 약 85.37초, rename/drop/index rename lock window는 약 1.06초.
- 실제 DB semantic parity test는 `tests/integration/test_optional_real_postgres_text_search.py`로 통과했다.

**검증**:
- targeted unit/ruff, 실제 DB parity test, T-057 corpus before/after benchmark, generated `search_fuzzy` benchmark, helper 포함 shadow swap benchmark.

**후속**:
- T-061 PR merge 후 사용자 최신 순서에 따라 T-050 운영 hardening을 진행한다.

## 2026-05-28 23:58 (T-053 Admin UI C1~C10 상세 분석/수동 판정 콘솔)

**작업**: 사용자 재확인 의도를 먼저 문서에 구체화한 뒤 C1~C10 sample 분석/판정용 backend API와 admin UI를 구현했다.

**반영**:
- `docs/t053-admin-ui-ops-statistics.md`에 C1~C10 기준 설명, 지도 overlay, table 비교, 단건/bulk 승인·거절·보류, recheck, v1/v2 API 경계를 정리했다.
- `ops.consistency_case_samples` DDL/Alembic을 추가하고 `run_all_cases()`가 report JSONB 요약과 sample row를 함께 저장하도록 바꿨다. 기존 report는 sample 조회 시 lazy backfill한다.
- `/v1/admin/consistency/case-definitions`, sample list/summary, 단건·bulk decision, recheck, CSV export API와 `AsyncAddressClient` 메서드를 추가했다.
- `/admin/consistency/[report_id]` 상세 화면을 추가하고 TanStack Query, TanStack Table, Zustand, `maplibre-vworld-js` wrapper 기반 지도 preview를 연결했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입을 갱신했고, Zustand/query helper 테스트를 추가했다.

**검증**:
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`
- `scripts/export_openapi.py --check --output openapi.json`
- `kor-travel-geo-ui`: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`

**후속**:
- T-053 PR merge 후 사용자 최신 지시에 따라 T-061 Q3 fuzzy slim text-search 구조를 먼저 진행한다.

## 2026-05-28 22:39 (PR #69 리뷰 반영 — v2 candidate distance/precision 보강)

**작업**: PR #69 formal review의 provider 비교 코멘트를 T-052 PR에 바로 반영했다.

**반영**:
- `CandidateV2.distance_m`을 first-class 필드로 추가하고 reverse 변환에서 `metadata.distance_m`와 함께 채운다.
- reverse v2 `confidence`를 고정 `1.0`에서 `1 - distance_m / radius_m` 기반 근접도 점수로 바꿨다.
- `CandidateV2.point_precision` enum을 추가하고, 현재 채움 범위와 후속 `pt_source` 연결 필요성을 API reference에 명시했다.
- `V2Source`가 현재 구현 가능한 `local`/`vworld`/`juso`/`cache`만 허용하며 Kakao/Naver/Google live adapter는 별도 task/ADR에서 확장한다는 문구를 보강했다.

**검증**:
- PR #69 commit 갱신 전 targeted/unit/OpenAPI/frontend type 검증을 다시 수행한다.

## 2026-05-28 20:43 (T-052 API v1/v2 분리와 AI-friendly 문서화)

**작업**: vworld 호환 v1 표면을 유지하면서 신규 v2 candidate schema와 API reference를 추가했다.

**반영**:
- 사용자 재확인에 따라 v2는 Kakao/Naver/Google/VWorld 직접 wrapper가 아니라 각 API 스타일의 장점을 참고한 `kor-travel-geo` 자체 API로 정리했다.
- `src/kortravelgeo/dto/v2.py`, `core/v2.py`, `api/routers/v2.py`를 추가하고 `/v2/geocode`, `/v2/reverse`, `/v2/search`를 연결했다.
- `AsyncAddressClient.geocode_v2()`, `reverse_v2()`, `search_v2()`를 추가했다.
- `docs/api-reference/`와 LLM 요약 문서를 추가했고, `openapi.json` 및 `kor-travel-geo-ui` 생성 타입을 갱신했다.
- v1 외부 fallback은 기존 ADR-019의 vworld/juso만 유지하고, Kakao/Naver/Google 호출과 새 API key는 추가하지 않았다.

**후속**:
- T-052 PR merge 후 T-053 코딩 전에 먼저 C1~C10 분석/판별/승인 UI 요구를 문서에 상세화한다.
- T-053 완료 뒤에는 사용자 최신 지시에 따라 T-061 Q3 fuzzy slim text-search를 먼저 진행한다.

## 2026-05-28 19:48 (T-052/T-053 선행 정리 — PR #67 리뷰 후속)

**작업**: PR #67 리뷰 후속과 사용자 확인사항을 T-052/T-053 본작업 전 선행 정리로 반영했다.

**반영**:
- 사용자 확인에 따라 T-056 RFC의 "조합/분리"는 주소 문자열 parse/compose가 아니라 코드 식별자의 조합·분해·정규화 의도였음을 문서화했다.
- 엄밀하지 않은 `clean-room` 표현을 "공개 주소 코드 규칙 기반 독립 구현, GPL 원본 코드 미복사"로 바로잡았다.
- Juso 검색 결과에 `admCd`/`rnMgtSn` 등 좌표 API 필수 코드가 없으면 coord API를 호출하지 않고 graceful `None`으로 끝나는 회귀 테스트를 추가했다.

**후속**:
- 이 선행 정리 PR을 머지한 뒤 T-052 v1/v2 API/provider 작업을 시작한다.

## 2026-05-28 19:20 (T-056 `python-legacy-address-base` Address 코드 helper 정리)

**작업**: `~/dev/python-legacy-address-base`의 실제 Address 표면을 확인하고, 본 저장소에서 필요한 주소 코드 helper를 clean-room으로 구현했다.

**확인**:
- `/home/digitie/dev/python-legacy-address-base`는 Git checkout이 아니었다. `.git`이 없어 `git rev-parse HEAD`는 실패했다.
- package license는 `GPL-3.0-or-later`였고, 본 저장소는 MIT이므로 원본 코드를 복사하지 않았다.
- 실제 Address 표면은 예상했던 `legacy.address_base.address.*` package가 아니라 `src/legacy/address-base/addresses.py` 단일 파일이었다.

**반영**:
- `src/kortravelgeo/core/address/codes.py`에 `SigunguCode`, `LegalDongCode`, `RoadNameCode`, `RoadNameAddressCode`, `AddressCodeSet`과 mapping/정규화 helper를 추가했다.
- Juso fallback 좌표 API 호출은 `AddressCodeSet`으로 `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`를 정규화한 뒤 요청한다.
- `docs/t056-legacy-address-base-address-merge.md`, ADR-035, 백엔드/아키텍처 문서, resume/tasks/CHANGELOG를 갱신했다.

**후속**:
- 사용자 최신 지시에 따라 T-056 이후에는 T-052/T-053 선행 정리 → T-052 → T-053 순서로 진행한다.

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 0.1.0 기준으로 upstream code/API를 재확인하고, upstream 코드는 직접 수정하지 않은 채 이 저장소 문서에만 T-044 보완점을 반영했다.

**확인**:
- GitHub tag `v0.1.0`은 commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb`이고, commit message는 `chore: release v0.1.0`이다.
- GitHub release는 없었고, npm registry에서도 `maplibre-vworld@0.1.0`과 `maplibre-vworld-js@0.1.0`은 `E404`였다.
- package name/version은 `maplibre-vworld`/`0.1.0`이며, `dist/`, `exports`, `types`, `style.css`, `VWorldMap`, marker/layer primitive, VWorld helper가 포함되어 있었다.
- 현재 `kor-travel-geo-ui` dependency는 여전히 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`에 고정되어 있고, 이번 작업에서는 dependency를 갱신하지 않았다.

**결론**:
- T-044는 0.1.0 기준 문서-only 재확인으로 완료한다.
- 실제 `CoordinateMap` 전환은 별도 구현 PR에서 `VWorldMap`/`Marker`/`PolygonArea` 소비를 검토한다.
- upstream 범용 기능 보강이 필요하면 이번 T-044 안에서 수정하지 않고 별도 upstream task/PR로 분리한다.

**문서**:
- `docs/t044-maplibre-vworld-010-review.md`
- `docs/tasks.md`
- `docs/frontend-package.md`
- `docs/external-apis.md`
- `docs/decisions.md`
- `docs/resume.md`

**검증**:
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
- 전체 pytest 결과는 216 passed, 6 skipped, 3 warnings다.

## 2026-05-28 17:42 (T-062 PR #53~#64 리뷰 audit/fixup)

**작업**: T-057 merge 직후 사용자 지시에 따라 PR #53부터 #64까지 아직 별도 audit하지 않은 PR 리뷰를 모두 재확인했다.

**확인**:
- 각 PR의 conversation comment, formal review, inline review thread, GraphQL `reviewThreads`를 확인했다.
- 모든 PR의 unresolved review thread는 0건이었다.

**직접 반영**:
- PR #53: search exact preflight의 Python/SQL 정규화 규칙을 문서화하고, shadow MV index 문서 오타를 수정했다. exact preflight가 없는 broad trigram fallback을 계속 측정하도록 `search_fuzzy` benchmark case와 REST 변환 case를 추가했다.
- PR #55: `pg_stat_statements` 조회/reset을 `x_extension` schema-qualified SQL로 고정했다.
- PR #59: reverse 좌표 bounds validation을 `PydanticCustomError("kor_travel_geo.coordinate_bounds", ...)` 기반 structured mapping으로 바꿔 문자열 전체 매칭 의존을 제거했다.
- PR #62: REST admission repeat 문서에 c64 tail 중심 비교 이유를 추가했다.
- PR #63: `tar.zst` SHA256 checksum 시간을 측정하고, backup envelope와 `tar.zst`의 의미를 단일 artifact 포장/checksum 단순화 중심으로 보강했다.

**후속**:
- 다음 작업은 사용자 추가 지시에 따라 T-044를 `maplibre-vworld-js` 0.1.0 기준으로 다시 확인하는 문서-only PR이다. upstream 코드는 직접 수정하지 않고 `kor-travel-geo` 문서에 보완점을 남긴다.

**검증**:
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
- 전체 pytest 결과는 216 passed, 6 skipped, 3 warnings다.

## 2026-05-28 16:20 (T-057 행정구역 hint 기반 검색 가속)

**작업**: `sig_cd`/`bjd_cd` 명시 hint를 라이브러리와 REST API, raw SQL repository, T-047 SQL/REST benchmark harness에 연결했다.

**반영 상세**:
- `RegionHint` DTO를 추가했다. `sig_cd`는 2자리 시도 prefix 또는 5자리 시군구 코드, `bjd_cd`는 8자리 법정동 prefix 또는 10자리 법정동 코드를 받는다.
- `/v1/address/geocode`, `/v1/address/search`, `/v1/address/reverse`는 선택 `sig_cd`/`bjd_cd` query parameter를 받는다.
- 응답 구조는 vworld 호환 그대로 유지한다. hint가 있는 geocode 요청에서 로컬 `NOT_FOUND`가 나오면 외부 fallback은 호출하지 않는다.
- 현재 `mv_geocode_target`에는 물리 `sig_cd`가 없으므로 `sig_cd`는 `bjd_cd` prefix filter로 적용한다.
- OpenAPI와 프론트엔드 생성 타입을 갱신했다.

**측정**:
- SQL standard artifact: `artifacts/perf/t057-region-hint-standard-20260528`.
- SQL corpus SHA: `e38bff5631a3b68fe6094e9124641a22f24770b9a040e8a70d067f1ea651d61f`.
- SQL run: 900 case, 8,100 measurement, error 0.
- SQL Q3 fuzzy c64 p95: 307.45ms → 267.99ms.
- REST smoke artifact: `artifacts/perf/t057-region-hint-rest-smoke-20260528`.
- REST run: 320 case, 1,920 measurement, error 0.
- REST Q3 fuzzy c64 p95: 651.62ms → 520.43ms.

**결론**:
- 명시 region hint는 유지할 가치가 있다.
- Q3 fuzzy는 hint로 개선되지만 충분한 종결 조건은 아니다. wide no-hint 경로가 일부 더 낮게 나와 trgm 후보 폭 자체를 줄이는 구조가 필요하다.
- 후속은 T-061 `mv_geocode_text_search` 또는 동등한 slim text-search 후보 테이블로 분리한다.
- T-057 PR merge 뒤에는 사용자 지시에 따라 최근 PR 중 리뷰를 아직 확인하지 않은 항목을 모두 audit/fixup한 뒤 다음 task로 넘어간다.

## 2026-05-28 14:56 (T-047 backup archive 압축 측정)

**작업**: T-047 인덱스 운영 영향 측정에서 남겨 둔 `tar.zst` archive 단계를 실제 `zstd` CLI로 측정했다.

**측정**:
- `apt download zstd` 후 `/tmp/codex-zstd/usr/bin/zstd`를 사용했다.
- zstd: `v1.5.5`.
- 입력: `artifacts/perf/t047-operational-impact-20260528/pgdump-dir`.
- 출력: `artifacts/perf/t047-operational-impact-20260528/pgdump-dir.tar.zst`.
- 명령: `tar --use-compress-program=/tmp/codex-zstd/usr/bin/zstd\ -T0\ -3`.
- archive wall time: 33.31초.
- max RSS: 112,768KiB.
- dump directory bytes: 4,313,361,824.
- archive bytes: 4,308,457,630.
- SHA256: `94f404bdf9a4a3956009f961f966e7bca3b90f42eecfc083e83add7b1ea87883`.

**결론**:
- `pg_dump -Fd` directory 내부의 대형 table data는 이미 `.dat.gz`라 `zstd` 포장 단계에서 크기 감소는 거의 없었다.
- archive 단계 자체는 33.31초로 짧았다. 전국 DB 백업 envelope는 `pg_dump -Fd` 2분 21.60초 + archive 33.31초 + checksum 단계로 보면 된다.
- T-047 자체 잔여였던 backup archive 측정은 완료했다. Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 후속으로 넘긴다.

## 2026-05-28 14:35 (T-047 REST admission candidate 반복 측정)

**작업**: REST worker/pool/admission exploratory grid에서 후보로 남긴 `w2/p8/a8`, `w4/p4/a4`를 기본 profile과 함께 `iterations=3`으로 반복 측정했다.

**측정**:
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- 각 run은 REST case 1,000건, measurement 16,000건, `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, error 0이었다.
- artifacts:
  - `artifacts/perf/t047-rest-repeat-default-20260528`
  - `artifacts/perf/t047-rest-repeat-w2-p8-a8-20260528`
  - `artifacts/perf/t047-rest-repeat-w4-p4-a4-20260528`

**결론**:
- `w2/p8/a8`은 Q1 road/Q4 search의 c64 p95와 Q1~Q4 p99가 더 안정적이었다. Q4 search p95는 default 873.12ms에서 596.35ms로 줄었다.
- `w4/p4/a4`는 Q7 zipcode, Q8 no-result, Q11 SPPN에서 가장 안정적이었다. Q8 no-result p95는 default 703.92ms에서 542.88ms로 줄었다.
- Q3 fuzzy는 p95 기준 default가 654.86ms로 가장 낮았고, p99 기준으로만 `w2/p8/a8`이 가장 낮았다. worker/pool/admission 조합만으로 Q3를 해결했다고 보지 않는다.

**후속**:
- T-047 안에서 pool 기본값을 더 바꾸지 않고, Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 실험으로 넘긴다.
- 남은 T-047 자체 작업은 `zstd` 준비 후 backup `tar.zst` archive 측정 정도다.

## 2026-05-28 14:06 (T-047 REST worker/pool/admission grid)

**작업**: REST API c64 tail을 줄이기 위해 `/v1/address/*` 전용 optional admission control을 추가하고, worker/pool/admission 조합을 exploratory benchmark로 비교했다.

**반영 상세**:
- `KTG_API_MAX_CONCURRENCY`가 설정된 경우에만 주소 API 요청을 process-local semaphore로 제한한다. 기본값은 unset이라 기존 동작은 유지된다.
- `KTG_API_ADMISSION_TIMEOUT_MS`는 semaphore 대기 timeout이다. timeout 시 HTTP 429 + `E0200`을 반환한다.
- health/admin/metrics 경로는 admission control 대상에서 제외했다.

**측정**:
- 기준 corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- 각 run은 REST case 1,000건, measurement 8,000건, `iterations=1`, `warmup=1`, concurrency `1/4/16/64`, error 0이었다.
- artifacts:
  - `artifacts/perf/t047-rest-grid-w1-p16-a16-20260528`
  - `artifacts/perf/t047-rest-grid-w2-p8-a8-20260528`
  - `artifacts/perf/t047-rest-grid-w4-p4-a4-20260528`

**결론**:
- `w4/p4/a4`는 Q4 search c64 p95를 753.25ms에서 435.63ms로, Q3 fuzzy를 810.53ms에서 550.35ms로 낮췄다. Q1/Q2/Q7도 개선됐다.
- `w2/p8/a8`은 Q6 reverse radius, Q8 no-result, Q11 SPPN reverse에서 더 안정적이었다.
- Q5 reverse nearest와 일부 p99는 아직 악화 구간이 있어 운영 권장값으로 확정하지 않는다.

**후속**:
- `w4/p4/a4`와 `w2/p8/a8`을 `iterations=3` 이상으로 재측정한다.
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 이어간다.

## 2026-05-28 13:19 (T-047 REST API pool64 비교)

**작업**: REST API e2e latency에서 DB pool만 64로 키웠을 때 c64 tail이 개선되는지 확인했다.

**측정**:
- artifact: `artifacts/perf/t047-rest-e2e-pool64-20260528`.
- 비교 기준: `artifacts/perf/t047-rest-e2e-standard-20260528-r2`.
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- uvicorn 단일 process, `KTG_PG_POOL_SIZE=64`, `KTG_PG_MAX_OVERFLOW=0`.
- REST case 1,000건, measurement 8,000건, error 0.

**결론**:
- Q3 fuzzy c64 p95는 810.53ms에서 557.25ms로 개선됐고, Q6 reverse radius p95는 773.89ms에서 757.39ms로 소폭 개선됐다.
- Q1/Q2/Q4/Q5/Q7/Q8은 대부분 악화됐다. 예를 들어 Q4 search c64 p95는 753.25ms에서 864.84ms로, Q1 도로명 geocode c64 p95는 581.42ms에서 850.38ms로 커졌다.
- REST 단일 process에서는 pool64가 checkout 대기만 줄이는 해법이 아니라 DB 동시 실행과 Python/HTTP scheduling 경합을 키울 수 있다. 운영 기본 pool을 64로 단순 상향하지 않고, 다음 실험은 worker 수, pool size, admission control 조합 grid로 진행한다.

**후속**:
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 SQL/REST 전후를 비교한다.
- API worker/pool/admission control grid를 같은 REST corpus로 측정한다.

## 2026-05-28 12:57 (T-047 REST API e2e latency)

**작업**: SQL benchmark corpus를 실제 `/v1/address/*` HTTP 요청으로 변환하는 REST API benchmark harness를 추가하고, 표준 corpus e2e latency를 측정했다.

**반영 상세**:
- `scripts/benchmark_api_latency.py`를 추가했다. 저장 corpus를 geocode/reverse/search/zipcode 요청으로 변환하고 `benchmark.json`, `summary.md`, `api-cases.json`, `environment.json`을 남긴다.
- SQL-only invalid reverse case `(0, 0)`은 public REST DTO에서 한국 밖 좌표로 거절되는 것이 맞으므로 REST latency corpus에서 제외했다.
- 내부 `pydantic.ValidationError`가 FastAPI exception handler를 지나 HTTP 500이 되던 문제를 보정했다. 한국 밖 reverse 좌표는 이제 HTTP 400 + `E0102`로 응답한다.

**측정**:
- artifact: `artifacts/perf/t047-rest-e2e-standard-20260528-r2`.
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- REST case 1,000건, measurement 8,000건, error 0.
- c1 p95는 6.95~16.18ms, c16 p95는 43.79~97.13ms였다.
- c64 p95는 Q3 fuzzy 810.53ms, Q6 reverse radius 773.89ms, Q4 search 753.25ms, Q7 zipcode point 734.30ms 순이었다.

**후속**:
- API worker 수, DB pool size, admission control 조합을 e2e로 비교한다.
- Q3 fuzzy는 REST tail도 가장 크므로 T-057 region hint 또는 `mv_geocode_text_search` 후보 실험을 유지한다.

## 2026-05-28 12:26 (T-047 stress corpus benchmark)

**작업**: PR #51/#52 후속 액션 중 `stress` 10,000건 이상 corpus 조건을 실제 T-027 Docker DB에서 측정했다.

**측정**:
- corpus: `artifacts/perf/t047-stress-20260528/corpus.json`, SHA `2123e09e41f96760b4a8451d98518a87aee6289cc8b238b8a8b2896b51665f23`, 11,000건.
- run: 기본 pool `size=10`, `max_overflow=5`, `iterations=1`, `warmup=1`, concurrency `1/4/16/64`.
- measurement 88,000건, error 0, `pg_stat_statements=true`.
- c16까지는 모든 query군 p95가 34ms 이하로 들어왔다.
- c64 tail은 대부분 checkout 대기였다. Q3 fuzzy p95 335.01ms 중 checkout p95 304.91ms, execute p95 32.07ms였고, Q4 search p95 302.21ms 중 checkout p95 280.41ms, execute p95 27.77ms였다.
- `pg_stat_statements` delta top은 Q3 fuzzy 계열 40,910.80ms/8,000 calls, Q1 road exact 21,453.97ms/8,000 calls, Q4 search 18,161.25ms/8,000 calls 순이었다.

**후속**:
- 다음 T-047 측정은 REST API e2e latency에서 HTTP overhead와 DB checkout/execute split을 대조한다.
- Q3 fuzzy 총 execution time이 가장 크므로 T-057 region hint 또는 `mv_geocode_text_search` 후보 실험은 유지한다.

## 2026-05-28 12:06 (T-047 인덱스 운영 영향 측정)

**작업**: T-047 exact btree index 3개(`idx_mv_jibun_name_exact`, `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`)가 MV refresh/swap, 디스크, 백업 단계에 주는 운영 영향을 실측했다.

**측정**:
- DB: Docker PostGIS `localhost:15432`, `mv_geocode_target=6,416,637`.
- 첫 shadow `swap`은 기본 statement timeout 5초에 걸려 실패했다. `mv_geocode_target_next`/`mv_geocode_target_old` 잔여 객체는 없었고 live MV row count는 유지됐다.
- `KTG_PG_STATEMENT_TIMEOUT_MS=1800000`으로 재실행한 결과, `CONCURRENTLY` refresh는 133.28초, shadow `swap`은 352.85초였다.
- T-035 기준선 대비 `CONCURRENTLY`는 +21.64초, shadow `swap`은 +215.70초다.
- shadow `swap` 중 exact index 3개 build phase 합계는 180.35초였다. live rename/drop/index rename 구간은 0.03초 수준으로 lock window는 여전히 짧았다.
- DB 전체는 31.90GiB, `mv_geocode_target` total은 4.78GiB, MV index total은 2.93GiB, exact index 3개 합계는 1.43GiB였다.
- `pg_dump -Fd --jobs=4` dump directory 생성은 2분 21.60초, 4.02GiB, max RSS 32,200KiB였다.

**산출물**:
- `artifacts/perf/t047-operational-impact-20260528/mv-concurrent.json`
- `artifacts/perf/t047-operational-impact-20260528/mv-swap.json`
- `artifacts/perf/t047-operational-impact-20260528/pgdump.time`

**후속**:
- 현재 WSL 환경에는 `zstd` CLI가 없어 최종 `tar.zst` archive 측정은 수행하지 못했다. 다음 backup archive 측정 전 `zstd` 설치 또는 backup helper fallback 압축 경로를 검증한다.
- T-047 다음 순서는 `stress` 10,000건 이상 corpus, REST API e2e latency, Q3 fuzzy 후보 축소다.

## 2026-05-28 11:20 (T-047 active observability run)

**작업**: T-047 관측성 보강이 머지된 뒤, 실제 Docker DB에 `pg_stat_statements`를 활성화하고 저장 corpus로 반복 benchmark를 수행했다.

**DB 조치**:
- `kor-travel-geo-t027-db-1` 컨테이너를 `shared_preload_libraries=pg_stat_statements` 설정으로 재생성했다. bind mount `/home/digitie/kor-travel-geo-data/pgdata`는 유지했다.
- 기존 DB는 Alembic version table이 없어 `alembic upgrade head`가 0001부터 시작했고, 33자 revision ID `0005_t039_roadaddr_entrance_table`가 기본 `varchar(32)`에 걸리는 문제가 드러났다.
- revision ID를 `0005_t039_roadaddr_entrc`로 줄이고, 모든 revision/down_revision 길이 32자 이하 테스트를 추가했다.
- 이 실측 DB는 이미 스키마 객체가 존재하는 수동 full-load DB라 `pg_stat_statements` extension을 직접 만든 뒤 `alembic stamp head`로 현재 상태를 기록했다.

**측정**:
- corpus: `artifacts/perf/t047-search-exact-split-20260528/corpus.json`, SHA `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`, 1,100건.
- 기본 pool run: `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, measurement 17,600건, error 0, `pg_stat_statements=true`.
- pool64 run: 같은 corpus, `pool_size=64`, `max_overflow=0`, concurrency 64, measurement 4,400건, error 0.
- 기본 pool c64는 Q4 search p95 330.80ms 중 checkout p95 307.88ms, execute p95 28.09ms로 대부분 connection checkout 대기였다.
- pool64 c64는 Q4 search p95 162.50ms, checkout p95 28.12ms, execute p95 128.11ms로 pool 대기는 줄었지만 DB 실행 시간이 커졌다. Q3 fuzzy는 pool64 c64 p95 167.87ms, execute p95 128.72ms로 다음 후보 축소 대상이다.

**산출물**:
- `artifacts/perf/t047-active-observability-20260528`
- `artifacts/perf/t047-active-observability-pool64-20260528`

**후속**:
- T-047 인덱스 3개의 운영 영향(MV refresh/swap, backup archive, 디스크 envelope)을 측정한다.
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 비교한다.

## 2026-05-28 10:35 (T-047 관측성 benchmark 보강)

**작업**: PR #51/#52 후속 액션 중 `pg_stat_statements`와 pool wait/DB execution 분리를 benchmark harness에 반영했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`의 artifact schema를 2로 올리고, measurement에 `checkout_ms`와 `execute_ms`를 추가했다.
- summary에는 `p95_checkout_ms`와 `p95_execute_ms`를 추가해 동시성 tail에서 connection pool 대기와 SQL 실행 시간을 분리해 볼 수 있게 했다.
- `pg-stat-statements-before.json`, `pg-stat-statements-after.json`, `pg-stat-statements-delta.json` artifact를 추가하고, `--reset-pg-stat-statements`, `--pg-stat-limit` 옵션을 넣었다.
- 당시 인프라 설정 파일, fresh schema SQL, Alembic `0011_t047_pg_stat_statements`에 `pg_stat_statements` preload/extension 경로를 추가했다.

**검증**:
- T-027 클린 DB(`localhost:15432`, `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204`)에서 `cases_per_group=1`, `iterations=1`, `warmup=0`, `concurrency=1` smoke benchmark를 실행했다.
- smoke 11개 query군은 모두 error 0이었다. 현재 기존 DB는 `pg_stat_statements` extension 미설치 상태라 snapshot artifact는 `available=false`, `error=pg_stat_statements extension is not installed`를 기록했다.

**후속**:
- Docker DB를 restart/upgrade한 뒤 `--reset-pg-stat-statements`와 저장 corpus로 `standard --iterations 3`를 다시 실행한다.
- T-047 인덱스 3개(`idx_mv_jibun_name_exact`, `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`)의 MV refresh/swap, backup archive, 디스크 envelope 영향을 별도 PR에서 측정한다.

## 2026-05-28 09:45 (PR #51/#52 post-merge 리뷰 반영)

**작업**: 사용자 지시에 따라 PR #51과 PR #52의 post-merge 리뷰 코멘트를 다시 확인하고, 후속 액션을 진행 가능한 문서 상태로 정리했다.

**확인 결과**:
- PR #51: conversation comment 1건, review 0건, review thread 0건.
- PR #52: conversation comment 1건, review 0건, review thread 0건.
- 두 PR 모두 unresolved inline thread는 없었다.

**반영 상세**:
- `docs/postmerge-review-fixups-pr51-pr52.md`를 추가해 리뷰 항목별 처리 상태를 정리했다.
- `docs/t047-query-performance-tuning.md`에 corpus 생성 알고리즘, 후보 확정 run profile, PR #51/#52 후속 액션 표를 보강했다.
- `docs/tasks.md`에서 T-060을 완료로 옮기고, 남은 T-047 후속을 `pg_stat_statements`, `standard --iterations 3`, stress corpus, pool wait/DB execution 분리, T-047 index 운영 영향, Q3 fuzzy/T-057 region hint로 명확히 정리했다.
- `docs/resume.md`와 `CHANGELOG.md`를 동기화했다.

**후속**:
- 다음 T-047 측정 PR은 관측성/운영 영향 묶음으로 시작하는 것이 자연스럽다. 단, 운영 안전성 우선순위를 더 엄격히 적용하면 T-056부터 진행한다.

## 2026-05-28 08:55 (T-047 Q4 search exact preflight 튜닝)

**작업**: Q4 통합 search의 broad trigram 병목을 줄이기 위해 exact preflight 경로와 전용 btree index를 추가했다.

**반영 상세**:
- `src/kortravelgeo/infra/search_repo.py`: search repository가 공백 제거 query로 `rn_nrm`/`buld_nm_nrm` exact preflight를 먼저 실행하고, exact 결과가 있으면 그 결과 집합만 반환한다. exact 결과가 없을 때만 기존 broad trigram search로 fallback한다.
- `src/kortravelgeo/infra/sql.py`, `alembic/versions/0010_t047_search_exact_indexes.py`: `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`를 추가했다.
- `scripts/benchmark_query_performance.py`: Q4 search benchmark가 raw `_SEARCH_SQL`만 직접 실행하지 않고 운영 repository와 같은 exact preflight를 재현하도록 수정했다.
- `tests/unit/test_infra_repo_sql.py`, `tests/unit/test_query_performance_benchmark.py`: SQL/index 계약과 benchmark search preflight 파라미터를 고정했다.

**측정**:
- 실제 T-027 클린 DB에서 index build time/size: `idx_mv_rn_nrm_exact` 120.45초/389MiB, `idx_mv_buld_nm_nrm_exact` 51.90초/316MiB.
- standard corpus Q4 100건은 모두 exact preflight로 처리됐다(`min_exact_total=13`, `max_exact_total=1,562`).
- `Q4-search-038`(`퇴계로88나길`) plan execution은 broad trigram 42.39ms → exact preflight 0.56ms로 감소했다.
- Q4 p95: default pool c1/c4/c16은 62.12/70.62/116.06ms → 12.23/22.39/52.27ms, pool64 c64는 481.22ms → 295.85ms. default pool c64는 pool 대기와 다른 query군 경합이 섞여 421.36ms → 622.38ms로 악화되어 SQL 효과 판단값으로 쓰지 않는다.

**후속**:
- 사용자 지시에 따라 현재 PR 머지 후 PR #51/#52 리뷰 코멘트를 다시 확인하고, actionable 항목 또는 후속 액션을 문서화한다.
- T-047 남은 항목은 `pg_stat_statements`, REST API e2e latency, stress 10,000건 corpus, Q3 fuzzy 후보 축소, T-057 region hint 비교다.

## 2026-05-28 00:45 (T-047 standard corpus와 pool 비교)

**작업**: PR #51 머지 후 최신 `origin/main`에서 T-047 benchmark harness를 사용해 1,100건 standard corpus와 동시성 64 pool 비교를 수행했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`에 `--pool-size`, `--max-overflow` 옵션을 추가했다. `environment.json`과 `summary.md`에는 실제 pool 설정을 기록한다.
- 같은 corpus로 기본 pool(`pool_size=10`, `max_overflow=5`)과 pool 64(`pool_size=64`, `max_overflow=0`) 동시성 64를 비교했다.
- `docs/t047-query-performance-tuning.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`에 결과와 후속 후보를 기록했다.

**측정**:
- `t047-standard-20260528`: 1,100 cases, concurrency 1/4/16/64, warmup 1, measured iteration 1, error 0.
- 기본 pool에서 동시성 16까지는 모든 query군 p95가 ADR-031 1차 목표 안에 들어왔다. 동시성 64에서는 Q1/Q2/Q3/Q4/Q5/Q7/Q8 tail이 크게 증가했다.
- `t047-standard-pool64-20260528`: 같은 corpus, concurrency 64, pool 64, error 0. Q2 지번 exact p95는 339.66ms → 156.76ms, Q8 no-result road p95는 222.18ms → 122.75ms로 개선됐다. 반면 Q3 fuzzy p95는 353.92ms → 417.46ms, Q4 search p95는 421.36ms → 481.22ms로 악화됐다.

**검증**:
- `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py` 통과.
- `mypy scripts/benchmark_query_performance.py` 통과.
- `pytest tests/unit/test_query_performance_benchmark.py -q` 6건 통과.

**후속**:
- Q3/Q4는 pool 확대가 답이 아니므로 query split, `UNION ALL`, text-search slim MV 후보를 별도 trial로 검증한다.
- `pg_stat_statements` 활성화 또는 DB execution aggregate 대체 방식을 마련해 pool wait와 DB 실행 시간을 더 명확히 나눈다.
- REST API e2e latency와 T-057 region hint 비교를 이어간다.

## 2026-05-27 23:45 (T-047 1차 query benchmark harness + 지번 exact 튜닝)

**작업**: T-047 중단 지점을 최신 `main`(#50) 위로 복구하고, query benchmark harness와 첫 번째 실제 튜닝을 완료했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`를 추가했다. `mv_geocode_target`/`tl_sppn_makarea`에서 deterministic corpus를 만들고, geocode/reverse/search/zipcode raw SQL을 실행해 `corpus.json`, `benchmark.json`, `environment.json`, `summary.md`, slow sample `EXPLAIN` JSON을 `artifacts/perf/<run-id>/`에 저장한다.
- `tests/unit/test_query_performance_benchmark.py`를 추가해 percentile, warmup 제외 summary, parser 기본값, corpus JSON round-trip을 검증했다.
- T-027 최종 클린 DB(`mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204`)에서 smoke benchmark를 실행했다.
- Q2 지번 exact가 기존 `idx_mv_jibun(bjd_cd, ...)` 경로에서 느린 것을 확인하고, `idx_mv_jibun_name_exact(si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno, emd_nm, li_nm, pt_source, bd_mgt_sn)`를 추가했다. 기존 DB용 Alembic `0009_t047_jibun_name_exact_index`와 fresh MV SQL을 함께 갱신했다.
- CodeGraph MCP 설정(`.codex/config.toml`)과 관련 문서 보강을 최신 `main` 위에 보존했다.

**측정**:
- index build: 56.03초, 761MiB.
- 같은 corpus smoke 전후: Q2 지번 exact client latency 2830.59ms → 5.58ms, plan execution 333.417ms → 0.100ms.
- post-index small concurrency run: `cases_per_group=5`, `iterations=3`, `warmup=1`, 동시성 1/4/16. 단일 동시성의 모든 query군 p95가 ADR-031 1차 목표 안에 들어왔고, 동시성 16에서는 Q1/Q3/Q4 tail이 90~110ms 구간으로 증가했다.

**검증**:
- `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py` 통과.
- `pytest tests/unit/test_query_performance_benchmark.py -q` 6건 통과.
- 실제 DB smoke benchmark와 post-index concurrency benchmark 실행 완료. artifact는 ignore 대상인 `artifacts/perf/`에 보관했다.

**후속**:
- `standard`/`stress` corpus, 동시성 64, REST API end-to-end latency, `pg_stat_statements`, T-057 region hint 비교를 다음 T-047 후속 PR에서 진행한다.

## 2026-05-27 (사용자 RFC 반영 — T-052~T-059 백로그 + ADR-035~ADR-038)

**작업**: 사용자 RFC(restore hot-swap, vworld/kakao/naver multi-provider + v1/v2 API + AI-friendly 문서, Web UI 통계/유지보수/관리/튜닝 + C1~C10 분석 UI/CSV, CLI 동시 실행 보호, 한국 IP만 허용, N150/Odroid 환경 검토, `python-legacy-address-base` Address 부분 병합 + 외부 라이브러리 삭제, 행정구역 hint 검색 가속)를 task 8건과 ADR 4건으로 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- `docs/tasks.md`에 T-052~T-059 신규 항목 추가 + 우선순위 재정렬. 운영 안전성(T-056, T-058, T-059, T-054)을 먼저, 기능 보강(T-057, T-053, T-052) 다음, 운영 환경 비교(T-055)는 하드웨어 도착 후.
- `docs/decisions.md`에 ADR-035(`python-legacy-address-base` Address 흡수 + 외부 라이브러리 삭제), ADR-036(restore hot-swap `ALTER DATABASE RENAME` 기반), ADR-037(외부 IP 한국만 허용), ADR-038(API v1/v2 분리 + 외부 provider 흡수 + AI-friendly 문서)을 추가했다.
- 각 task별 design doc 8건 신규: `docs/t052-api-providers-v1-v2.md`, `docs/t053-admin-ui-ops-statistics.md`, `docs/t054-korea-only-geoip.md`, `docs/t055-deployment-n150-odroid.md`, `docs/t056-legacy-address-base-address-merge.md`, `docs/t057-region-hint-search.md`, `docs/t058-restore-hot-swap.md`, `docs/t059-concurrent-job-protection.md`.
- 각 design doc은 "상태/목적/현황/결정/구현 sketch/검증/남은 위험/관련 ADR-Task" 구조로 작성해 사람과 AI agent 모두가 cold start로 진입할 수 있게 했다.
- `CHANGELOG.md`/`docs/resume.md`에 같은 내용을 동기화했다.

**현황 확인 결과 (사용자가 "반영되어 있으면 스킵" 조건을 건 항목)**:
- restore hot-swap: 현 시점 `docs/t046-db-backup-restore.md`/ADR-030은 "기본 새 빈 DB + `replace_current` 위험 경로"만 명문화. hot-swap 절차 자체는 미반영 → **스킵하지 않고 T-058로 등록**.
- CLI 중복 실행 보호: in-process semaphore + `load_jobs` advisory lock + `TL_SPBD_BULD` staging lock + `ops.serving_releases` active partial unique는 이미 있음. cross-process 표준화는 일부만 적용 → **T-059로 인벤토리 + 표준화 등록**.

**다음 작업**: 우선순위에 따라 T-056부터 또는 T-027 베이스라인 활용 가능한 T-057/T-059부터 구현 PR을 만든다. 본 PR은 문서/계획만 포함하므로 코드/DDL은 후속 PR에서 처리한다.

**검증**:
- `git diff --check` 통과 예정(문서 전용).
- `pytest -q`, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`는 본 PR이 코드 변경이 없으므로 회귀 차원에서 baseline만 통과 확인.

## 2026-05-27 (T-047 중단 기록 — CodeGraph MCP 설정과 벤치마크 harness 초안)

**작업**: 사용자 지시에 따라 T-047 진행 중 Codex Desktop 재시작을 위해 작업을 중단하고 현재 상태를 기록했다. 이 시점에는 PR/commit/push를 하지 않았다.

**현재 branch/worktree**:
- worktree: `~/dev/geo-codex`
- branch: `agent/codex-t047-query-performance`
- 기준: `origin/main`

**반영된 미커밋 변경**:
- `.codex/config.toml`: CodeGraph MCP stdio 서버 설정 추가. `codegraph install --print-config codex`가 제안한 `command = "codegraph"`, `args = ["serve", "--mcp"]` 방식을 사용했다. WSL에서 `npx -y @colbymchenry/codegraph mcp`는 Windows npm shim/UNC 경로 경고가 발생할 수 있어 기본값으로 쓰지 않았다.
- `README.md`, `AGENTS.md`, `SKILL.md`, `docs/dev-environment.md`, `docs/agent-guide.md`, `docs/decisions.md`: CodeGraph `init -i`/`status`, MCP 재시작 필요성, 컴포넌트 수정 전 `codegraph_explore` 영향도 확인 규칙을 보강했다.
- `scripts/benchmark_query_performance.py`: T-047 query benchmark harness 초안 추가. `mv_geocode_target`, `tl_sppn_makarea`, zipcode/search/reverse/geocode SQL을 대상으로 corpus 생성, 반복 측정, summary/JSON/plan artifact 저장 구조를 작성했다.
- `tests/unit/test_query_performance_benchmark.py`: percentile, summary aggregation, corpus JSON round-trip 단위 테스트 추가.

**검증된 것**:
- `codegraph sync && codegraph status` 실행 결과 `Index is up to date`를 확인했다. sync 당시에는 새 Python 파일 2개가 인덱스에 반영됐다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=... /home/digitie/dev/kor-travel-geo/.venv/bin/python -m pytest tests/unit/test_query_performance_benchmark.py -q` 실행 결과 6건 통과.
- `ps` 확인 시 benchmark/pytest/ruff/gh/당시 인프라 명령 장기 실행 프로세스는 없었다.

**아직 끝나지 않은 것**:
- `scripts/benchmark_query_performance.py`와 테스트는 ruff를 한 차례 보정했지만, 마지막 상태에서 전체 `ruff`, `mypy`, 실제 Docker DB smoke benchmark를 아직 다시 실행하지 않았다.
- 실제 DB 스모크 benchmark, `EXPLAIN` plan artifact 생성, `docs/t047-query-performance-tuning.md` 구현 결과 보강, `docs/resume.md` 최종 완료 토글, `CHANGELOG.md` 갱신, commit/push/PR 생성은 남아 있다.
- Codex Desktop 재시작 전이므로 현재 세션에는 CodeGraph MCP 도구가 아직 노출되지 않는다. 재시작 후 `codegraph_explore` 도구가 보이면 UI 컴포넌트 작업 때 먼저 사용한다.

**재개 순서**:
1. Codex Desktop 재시작 후 `~/dev/geo-codex`에서 `git status --short --branch` 확인.
2. `codegraph sync && codegraph status` 실행.
3. `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py`를 venv Python으로 재실행.
4. 같은 단위 테스트를 다시 실행.
5. Docker DB `localhost:15432` 상태를 확인한 뒤 작은 T-047 smoke benchmark를 실행한다.

## 2026-05-27 (T-051 — 에이전트별 worktree와 CodeGraph 운용 문서화)

**작업**: 사용자 요청에 따라 ChatGPT Codex, Claude Code, Google Antigravity 2.0이 같은 checkout을 공유하지 않고 에이전트별 고정 Git worktree를 유지하는 정책을 문서화했다.

**반영 상세**:
- ADR-034를 추가해 `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree와 `agent/<agent>-*` branch prefix를 확정했다.
- `docs/dev-environment.md`에는 최초 `git worktree add` 절차, 새 작업 branch 생성 절차, CodeGraph `init -i`/`sync`/`status` 운용 절차를 상세히 적었다.
- `AGENTS.md`, `SKILL.md`, `README.md`, `docs/agent-guide.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`에 핵심 규칙을 동기화했다.
- `.codegraph/`를 `.gitignore`에 추가해 로컬 SQLite 인덱스가 PR diff에 섞이지 않게 했다.

**검증**:
- CodeGraph 원문 문서에서 `codegraph init -i`가 `.codegraph/` 생성과 즉시 인덱싱을 수행하고, 기존 인덱스는 `codegraph sync`로 증분 갱신한다는 점을 확인했다.
- 최초 확인 시 로컬 WSL PATH에는 Windows npm shim(`/mnt/c/Users/digit/AppData/Roaming/npm/codegraph`)이 먼저 잡히며 `node: not found`로 실패했다. CodeGraph Linux installer로 `v0.9.6`을 `~/.codegraph`/`~/.local/bin`에 설치한 뒤 `codegraph --version`이 정상 동작함을 확인했다.
- `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree를 생성했다. 각 worktree에서 `codegraph init -i && codegraph status`를 실행했고, 201 files, 2,796 nodes, 6,251 edges, DB size 5.58 MB, `node:sqlite`/WAL, `Index is up to date` 상태를 확인했다.
- `git diff --check`, `.venv/bin/ruff check .`, `.venv/bin/mypy src/kortravelgeo`, `.venv/bin/lint-imports`, `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`를 실행했다. 결과는 `191 passed, 6 skipped`다.

**후속**:
- 이후 모든 새 작업은 해당 에이전트 고정 worktree에서 branch만 새로 따고, branch 전환 뒤 `codegraph sync`로 인덱스를 맞춘다.

## 2026-05-27 (PR #34~#47 리뷰 코멘트 audit/fixup)

**작업**: 사용자 지시에 따라 PR #34부터 #47까지 GitHub conversation comment, formal review body, inline review thread, GraphQL `reviewThreads`를 다시 확인했다. PR #34~#43에는 post-merge 리뷰 코멘트가 있었고, PR #44는 Windows Playwright 확인 메모, PR #45~#47은 확인 시점 기준 신규 코멘트가 없었다. unresolved current review thread는 0개였다.

**반영 상세**:
- `docs/postmerge-review-fixups-pr34-latest.md`를 추가해 PR별 코멘트, 이번 반영, 후속 이관 항목, 재사용할 GraphQL query template을 기록했다.
- PR #35 M3 반영: `LoadJobStatus.source_set`, `ConsistencyReport.source_set`, 내부 row protocol, `run_all_cases(source_set=...)` 타입을 `dict[str, Any]`로 넓혀 `SourceSetPlan`의 nested JSON을 보존한다. `openapi.json`, `kor-travel-geo-ui/types/api.gen.ts`, `kor-travel-geo-ui/lib/api.ts`도 함께 갱신했다.
- PR #43 M5 반영: `ops.audit_events.job_id` FK를 `ON DELETE SET NULL`에서 `ON DELETE NO ACTION`으로 변경했다. fresh DDL과 Alembic `0008_pr34_review_followups`를 추가해 감사 이벤트와 job 연결이 조용히 끊기지 않게 했다.
- PR #38/PR #42 후속 반영: `maplibre-vworld-js` upstream `main` 최신 SHA `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`를 확인해 `kor-travel-geo-ui` dependency/lockfile과 문서를 갱신하고, Windows `npm` 오사용을 막는 `scripts/frontend_check.sh`를 추가했다.

**검증 계획**:
- 백엔드: `pytest`, `ruff`, `mypy`, `lint-imports`, OpenAPI drift check.
- 프론트엔드: WSL Linux Node/npm으로 `scripts/frontend_check.sh` 실행. Playwright는 사용자 지시에 따라 Windows Node/브라우저에서만 수행한다.

**후속**:
- T-050 운영 hardening을 백로그에 추가했다. upload set cleanup TTL/lock, callback HMAC/retry, backup/restore sub-progress, snapshot/release 자동 생성 hook, table stats cron, destructive confirmation flow, 실제 PostgreSQL constraint integration test를 묶어 처리한다.

## 2026-05-27 (T-027 — 최종 실 데이터 클린 적재와 same-month direct 출입구 gate)

**작업**: PR #46 머지 후 최신 main에서 Docker PostGIS DB를 비우고 실제 `data/juso` 원천을 처음부터 적재했다. `scripts/fullload_test.sh`를 T-038/T-039/T-042 이후 원천까지 포함하도록 보강하고, 전체 실행 로그·시스템 상태·row count·정합성 결과·data-quality export를 `artifacts/fullload/20260527_135155/`에 남겼다.

**반영 상세**:
- full-load script는 `tl_juso_parcel_link`, `tl_roadaddr_entrc`, `tl_sppn_makarea`를 함께 적재하고, source별 기준월(`JUSO=202603`, `LOCSUM/NAVI/SHP=202604`, `ROADADDR/SPPN=202605`)을 PLAN_ONLY와 로그에 명시한다.
- 실제 적재는 총 3,934초가 걸렸다. 주요 단계는 텍스트 825초, SHP 1,525초, direct 출입구 216초, SPPN 의무지역 33초, geometry link 140초, MV swap 159초였다.
- 최종 row count는 `tl_juso_text=6,416,637`, `tl_juso_parcel_link=1,769,370`, `tl_roadaddr_entrc=6,404,697`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,416,637`이다.
- direct 출입구를 기존 T-039 설계대로 1순위 serving 좌표로 쓰면 기준월 차이 때문에 C4/C6/C7이 악화됐다. `roadaddr` 우선 결과는 C4 12,225건(`over_500m=91`), C6 3,593건, C7 9,827건이었다.
- `tl_locsum_entrc`만 임시 비교하면 기존 기준선인 C4 3,415건(`over_500m=16`), C6 803건, C7 6,817건으로 돌아왔다. 이에 MV와 C3/C4/C6/C7/C8 serving CTE를 `locsum` 우선 + same-month `roadaddr` fallback으로 보정했다.
- C10은 `load_manifest`만 보던 한계를 수정해 row-level `source_yyyymm` 집계를 우선하고 manifest를 fallback으로 쓰게 했다. 현재 로컬 혼합 세트는 `distinct_months=3`, `severity=WARN`으로 기록된다.

**검증**:
- Targeted unit tests: `tests/unit/test_consistency_sql.py`, `tests/unit/test_infra_engine_pnu_sql.py` 통과.
- 보강 후 MV swap refresh 성공. `pt_source` 분포는 `centroid=3,496,182`, `entrance=2,906,372`, `NULL=14,083`이다.
- 보강 후 전체 C1~C10 재검증은 611.71초, 최대 RSS 82,424KB로 완료했다. `severity_max=ERROR`는 기존 C2/C4/C6/C7 원천 품질 이슈 때문이다.
- smoke test는 geocode/reverse/search/zipcode 모두 `OK`.
- data-quality export는 C2/C4/C6/C7 CSV 8개를 86.18초, 최대 RSS 82,292KB로 생성했다. C4 bucket은 `0-50=2,887,827`, `50-100=2,847`, `100-500=552`, `500+=16`이다.

**후속**:
- T-027 보강 PR을 열고 리뷰 대기 후 main에 머지한다.
- T-047은 이 클린 DB를 기준으로 query latency baseline과 튜닝 전후 차이를 기록한다.
- Playwright가 필요한 UI 검증은 사용자 지시에 따라 Windows Node/브라우저에서 수행한다.

## 2026-05-27 (T-042 — `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 구현)

**작업**: ADR-027의 `TL_SPPN_MAKAREA` 설계를 실제 DDL, loader, CLI/API job, source set optional child, geocode/reverse 보조 조회로 구현했다.

**반영 상세**:
- `tl_sppn_makarea` DDL과 Alembic `0007_t042_sppn_makarea`를 추가했다. 원천 `Polygon`은 운영 `MultiPolygon 5179`로 정규화한다.
- `load_sppn_makarea()`를 추가했다. `구역의 도형` ZIP, 디렉터리, 추출된 SHP 입력을 탐지하고 GDAL Python binding으로 staging table에 적재한 뒤 `SIG_CD + MAKAREA_ID` 기준으로 upsert한다.
- `ktgctl load sppn-makarea`, API queue kind `sppn_makarea_load`, source set optional `sppn_makarea` child를 연결했다.
- `core.sppn`에 국가지점번호 parser와 EPSG:5179 좌표 formatter를 추가했다.
- geocode는 국가지점번호 문자열을 좌표로 변환한 뒤 `ST_Covers(tl_sppn_makarea.geom, point)`로 검증하고, `x_extension.national_point_number`와 `x_extension.sppn_makarea`를 반환한다.
- reverse geocode는 도로명/지번 후보가 없어도 polygon 포함 여부가 있으면 `status="OK"`와 `x_extension.sppn_makarea`를 반환한다.
- 실제 적재 중 `REPLACE(col, chr(0), '')`가 PostgreSQL에서 `null character not permitted`를 유발하는 문제를 발견해 `NULLIF(BTRIM(col::text), '')`로 수정했다.

**검증**:
- Targeted unit/contract pytest 48건을 통과했다.
- Docker PostGIS `kor_travel_geo_t042_sppn`에 세종 `구역의 도형/구역의도형_전체분_세종특별자치시.zip`을 실제 적재했다. 결과는 146행, 146 distinct key, source_yyyymm `202605`, 전체 valid MultiPolygon이었다.
- timed load는 `elapsed_s=1.35`, `max_rss_kb=131092`였다.
- `금이산` polygon 내부 `ST_PointOnSurface()`를 formatter로 `다바 7363 4856`으로 변환했고, geocode/reverse 보조 조회가 모두 `makarea_id=29`, `makarea_nm=금이산`을 반환했다.
- optional integration test `test_real_postgres_can_load_sppn_makarea_and_lookup_when_dsn_is_set`를 실제 DB DSN으로 실행해 통과했다.

**후속**:
- T-027 최종 클린 로드에서 `sppn_makarea` optional source를 포함할지 결정하고, 포함 시 전국 row count와 시간을 기록한다.
- T-047 성능 벤치마크에 국가지점번호 geocode/reverse Q11을 포함한다.
- T-044에서 최신 `maplibre-vworld-js` wrapper 기반 `TL_SPPN_MAKAREA` polygon overlay를 추가한다.

## 2026-05-27 (T-046 — 적재 완료 DB 백업/복원 및 UI 구현)

**작업**: ADR-030의 적재 완료 DB 백업/복원 설계를 실제 DTO, 설정, 실행 로직, REST API, CLI, 관리 UI, 테스트, 대구광역시 부분 DB 검증으로 구현했다.

**반영 상세**:
- `db_backup`, `db_restore` job kind와 `BackupCreateRequest`, `RestoreCreateRequest`, `BackupArtifact` DTO를 추가했다.
- `KTG_BACKUP_ALLOWED_DIRS`, 임시 디렉터리, 병렬 jobs, 압축 level, TTL, callback allowlist, download token secret 설정을 추가했다.
- `infra.backup`에서 allowlist/symlink escape 검증, `pg_dump -Fd --jobs`, `.part` 기반 `tar.zst` archive, manifest/checksum, `pg_restore -Fd --jobs`, target DB empty/current DB guard, callback, HMAC download token을 구현했다.
- `pg_dump`/`pg_restore` password는 argv에 넣지 않고 `PGPASSWORD` 환경변수로 넘기도록 해 process argument와 log 노출을 줄였다.
- `ops.artifacts` helper를 확장해 `db_backup` artifact metadata를 저장하고, backup/restore 작업을 기존 영속 `load_jobs` 큐에 연결했다.
- `/v1/admin/backups`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events`, `ktgctl backup/restore`, `/admin/backups` UI를 추가했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입/schema를 갱신했다.

**검증**:
- Backend targeted pytest 32건, `ruff`, `mypy`를 통과했다.
- Frontend `eslint`, `tsc --noEmit`, `vitest`, `next build`를 통과했다.
- Playwright 검증은 사용자 지시에 따라 Windows Node에서 수행했다. `/admin/backups` 화면에서 백업 시작, 복원 시작, 다운로드 링크 노출을 API mock으로 확인했고 screenshot은 `C:\Users\digit\AppData\Local\Temp\t046-admin-backups-windows.png`에 저장했다.
- Docker PostGIS에서 대구광역시 부분 원천을 실제 적재한 뒤 `/tmp/kortravel-t046/backups/t046_daegu_backup.tar.zst` 백업과 새 DB 복원을 수행했다. 원본/복원 row count는 `tl_juso_text=228,875`, `tl_juso_parcel_link=26,594`, `tl_locsum_entrc=228,610`, `tl_navi_buld_centroid=291,281`, `mv_geocode_target=228,875`로 일치했고, `대구광역시 중구 공평로 88` geocode/reverse smoke test가 모두 `OK`였다.

**후속**:
- callback retry/backoff, restore 취소 시 target DB drop/quarantine 정책, 디스크 여유 공간 사전 추정, PostgreSQL/PostGIS major mismatch hard-fail은 hardening task로 남긴다.
- 전국 full-load 재실행과 전체 쿼리 성능 벤치마크는 T-027/T-047에서 진행한다.
- 다음 작업은 T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 구현이다.

## 2026-05-27 (T-045 — source set 기준월 선택과 대용량 업로드/적재 UX 구현)

**작업**: ADR-029의 source set 설계를 실제 DTO, 탐지/계획 helper, upload set 저장소, REST, 라이브러리, CLI, `/admin/load` UI와 테스트로 구현했다.

**반영 상세**:
- `SourceCandidate`, `SourceSetDiscovery`, `SourceSetPlan`, `UploadSetStatus`, `UploadFileStatus` DTO를 추가했다.
- `infra.source_set`에서 원천 후보를 자동 탐지하고, source kind별 기준월과 명시 `children` batch payload를 만드는 helper를 추가했다.
- `infra.uploads`에서 upload set을 JSON manifest로 영속화하고, raw stream 파일 저장, `*.part` atomic rename, sha256, 기준월/source kind 추론, 크기 제한 실패 상태, 취소를 구현했다.
- `/v1/admin/uploads/*`와 `/v1/admin/load-sources/*`를 추가하고, `/v1/admin/loads kind=full_load_batch`가 명시 child job 목록을 받도록 UI/라이브러리/CLI를 연결했다.
- `ktgctl load full-set`은 자동 발견 후 기준월이 섞이면 정확한 확인 문구 없이는 plan을 만들지 않는다.
- `/admin/load`는 다중 파일 선택과 DND, XHR upload progress, upload set cancel, source set review, 기준월 mismatch modal, 적재 진행률과 root job cancel을 제공한다.

**검증**:
- `tests/unit/test_source_set_plan.py`에서 source 탐지, optional 제외, 같은 기준월 plan, 혼합 기준월 확인, upload 저장/취소, 크기 제한 실패를 검증했다.
- `kor-travel-geo-ui/tests/unit/load-workflow.test.ts`에서 상태 전이, 확인 token 생성, 진행률 계산을 검증했다.
- 중간 검증으로 backend targeted pytest, backend ruff/mypy, frontend lint/type-check/load-workflow test를 통과했다. 최종 PR 검증에서는 전체 backend/frontend gate와 OpenAPI drift 검사를 다시 수행한다.

**후속**:
- C10 정합성 severity 조정은 `source_set.mixed_yyyymm_acknowledged`를 더 읽도록 별도 보강한다.
- `ops.dataset_snapshots`에 source set 확정 정보를 자동 연결하는 일은 T-027/T-047 full-load gate 보강 때 이어간다.
- 다음 작업은 T-046 백업/복원 구현이다.

## 2026-05-27 (T-049 — 운영 메타데이터·감사·릴리스 스키마 구현)

**작업**: ADR-033의 `ops` 운영 메타데이터 설계를 실제 DDL, Alembic migration, DTO/API/client, 관리 UI, 테스트로 구현했다.

**반영 상세**:
- `ops.audit_events`, `ops.dataset_snapshots`, `ops.serving_releases`, `ops.artifacts`, `ops.maintenance_windows`, `ops.table_stats_snapshots`를 `sql/ddl/001_schema.sql`과 `src/kortravelgeo/infra/sql.py`에 추가하고, 기존 DB upgrade용 Alembic `0006_t049_ops_metadata_schema.py`를 작성했다.
- `ops.audit_events`는 append-only trigger로 UPDATE/DELETE를 막고, `ops.serving_releases`는 `state='active'` partial unique index로 active release 한 건만 허용한다.
- `kortravelgeo.core.redaction`을 추가해 API key, DSN, password, token, callback secret, 주소 원문을 audit payload에 평문 저장하지 않도록 했다.
- `AdminRepository`, `AsyncAddressClient`, `/v1/admin/ops/*` API를 추가했다. audit event/snapshot/release/artifact/maintenance/table stats 조회, rollback plan, maintenance window 생성/종료, table stats snapshot capture를 제공한다.
- `kor-travel-geo-ui`에 `/admin/ops` 화면을 추가했다. release, snapshot, artifact, audit event, maintenance window, table stats snapshot을 조회하고 maintenance window 생성과 stats capture를 실행할 수 있다.
- OpenAPI와 frontend generated type/schema 목록을 갱신했다.

**검증**:
- `.venv/bin/python -m pytest -q` → 155 passed, 5 skipped.
- `.venv/bin/python -m ruff check .` 통과.
- `.venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` 통과.
- `.venv/bin/lint-imports` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run lint` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run type-check` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test` → 22 passed.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run build` 통과.

**남은 연결**:
- T-045/T-027에서 source set 확정과 full-load/daily completion을 `ops.dataset_snapshots`에 연결한다.
- T-046에서 backup/restore 산출물을 `ops.artifacts`에 등록한다.
- T-047에서 성능 리포트와 전후 table stats snapshot을 `ops.artifacts`/`ops.table_stats_snapshots`에 연결한다.
- MV swap 성공 시 `ops.serving_releases` active row 교체는 T-027/T-047 gate와 함께 보강한다.

## 2026-05-27 (T-043 — PR #23~#41 리뷰 코멘트 audit/fixup)

**작업**: 사용자 지시에 따라 PR #23부터 최신 PR #41까지 GitHub 리뷰 표면을 thread-aware로 다시 확인하고, 반영 가능한 항목을 코드/문서로 보강했다.

**반영 상세**:
- GraphQL `pullRequest.comments`, `reviews`, `reviewThreads`와 REST review comment API를 함께 조회했다. 대상 PR 전체에서 unresolved review thread는 0개였다.
- `kor-travel-geo-ui/lib/vworld.ts`의 `redactVWorldTileUrl` alias 수명 주석과 redaction test의 API key 누설 방지 assert를 추가했다.
- `kor-travel-geo-ui/README.md`에 WSL ext4에서는 Linux Node/npm을 사용하라는 검증 경고를 추가했다.
- `docs/t035-mv-refresh-benchmark.md`에 session/wait event metadata 해석 가이드를 보강했다.
- `docs/t028-daily-juso-delta.md`에 신규 `MVM_RES_CD` 대응 절차, dedup 정렬 전제, `No Data` sentinel, checksum, queue 직렬화, daily 후 MV refresh 정책을 추가했다.
- CLI의 `--limit-per-file` 옵션 사용 시 stderr 경고를 출력하도록 했다.
- `TL_SPBD_BULD` projection staging 경로에 advisory lock을 추가하고, staging row count 대비 insert row count 차이를 skip metric으로 출력하도록 했다.
- ADR-027에 `TL_SPPN_MAKAREA` 원천 `Polygon` → 운영 `MultiPolygon` 변환 원칙과 T-042 진입 전 남은 위험을 추가했다.
- 상세 audit 표와 후속 이관 항목은 `docs/postmerge-review-fixups-pr23-latest.md`에 남겼다.

**검증**:
- `git diff --check` 통과.
- `.venv/bin/python -m pytest -q` → 150 passed, 5 skipped.
- `.venv/bin/python -m ruff check .` 통과.
- `.venv/bin/python -m mypy src/kortravelgeo` 통과.
- `.venv/bin/lint-imports` 통과.
- 프론트엔드 로컬 검증은 Linux Node가 없고 Windows `npm`만 잡혀 UNC 경로 오류가 나므로 실행하지 않았다. GitHub Actions frontend job에서 확인한다.

## 2026-05-27 (문서 정합성 재검토와 task 순서 재정렬)

**작업**: 사용자 지시에 따라 `main` 최신 문서와 실제 CLI/최근 ADR 사이의 불일치를 전체적으로 재검토하고 문서에 반영했다. 코드는 작성하지 않았다.

**반영 상세**:
- README/SKILL의 현재 상태와 quick start를 갱신했다. `load all-sidos` 예시는 실제 CLI 옵션(`--juso`, `--jibun`, `--locsum`, `--navi`, `--shp-root`, `--yyyymm`) 기준으로 바꿨다.
- 현재형 문서의 브랜치 표현을 `master`에서 `main`으로 바로잡았다. 단, `master table` 같은 DB 도메인 용어와 과거 작업 일지의 역사적 표현은 유지했다.
- `SKILL.md`의 “백엔드만 다룬다” 설명을 같은 저장소 안의 별도 Node.js 패키지 `kor-travel-geo-ui`를 함께 관리한다는 설명으로 정리했다.
- T-046 백업 artifact metadata는 신규 구현에서 `ops.artifacts`로 수렴한다는 ADR-033 방향을 `docs/architecture.md`, `docs/t046-db-backup-restore.md`, `docs/decisions.md`에 맞췄다.
- `docs/tasks.md`와 `docs/resume.md`의 후속 순서를 T-043 → T-049 → T-045 → T-046 → T-042 → T-027 → T-047 → T-044로 재정렬했다. 데이터·운영 gate를 먼저 안정화한 뒤 지도 UI 경계화를 진행하는 순서다.
- 점검표와 남겨 둔 범위는 `docs/doc-consistency-audit-20260527.md`에 기록했다.

**검증**:
- `git diff --check` 통과.
- 현재 환경에는 `python` alias, `pytest`, `ruff`, `uv`가 없어 `pytest`/`ruff` 게이트는 실행하지 못했다. 후속 구현 작업 전 가상환경 복구가 필요하다.

## 2026-05-27 (README 법적 고지 — AI 활용 학습 목적과 데이터 준수 표기)

**작업**: 사용자 지시에 따라 README의 법적 고지에 프로젝트 목적과 데이터 사용 준수 원칙을 명시했다.

**반영 상세**:
- 이 프로젝트가 한국 주소 지오코딩 도메인을 대상으로 AI 활용 방식과 개발 워크플로를 학습·검증하기 위한 기술 연구 프로젝트임을 추가했다.
- 외부 원천 데이터와 API는 제공 기관의 이용약관, 저작권, 재배포 조건, 호출 한도를 준수하는 것을 전제로 사용하며 원천 데이터 자체를 저장소에 포함하지 않는다고 명시했다.
- 사용자 가시 문서 변경이므로 `CHANGELOG.md`에도 같은 요지를 남겼다.

## 2026-05-27 (T-049 등록 — 운영 메타데이터·감사·릴리스 스키마)

**작업**: 사용자 지시에 따라 유지보수와 관리 관점에서 추가해야 할 운영 기능, 테이블, 스키마를 ADR과 Task로 정리했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-033을 추가했다. 운영 메타데이터 전용 `ops` 스키마를 두고, 감사 이벤트, 데이터셋 snapshot, serving release, artifact registry, maintenance window, table stats snapshot을 관리하도록 결정했다.
- `docs/t049-ops-metadata-schema.md`를 추가했다. 각 테이블의 목적, 핵심 컬럼, API/UI 범위, 구현 순서, 검증 기준을 상세히 정리했다.
- `docs/tasks.md`에 T-049를 추가했다. destructive restore, schema migration, full reset은 active maintenance window와 typed confirmation 없이는 실패해야 한다는 요구도 포함했다.
- `docs/data-model.md`, `docs/architecture.md`, `README.md`, `CHANGELOG.md`, `docs/resume.md`를 같은 방향으로 갱신했다.

**결정**:
- `public`은 주소 원천·serving 객체, `x_extension`은 PostGIS 보조 extension, `ops`는 운영 제어면으로 분리한다.
- T-046의 `db_backup_artifacts`는 신규 구현에서는 `ops.artifacts`의 `artifact_type='db_backup'`으로 수렴한다.
- 감사 테이블에는 API key, DSN password, token, callback secret, 주소 원문을 평문 저장하지 않는다.

## 2026-05-27 (T-048 — `maplibre-vworld-js` 최신 동기화와 책임 경계 재정의)

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 사용 시 항상 최신 버전을 확인하고, 이 라이브러리의 특화 기능은 upstream `vworld.js`가 아니라 `kor-travel-geo-ui` 쪽에서 구현한다는 원칙을 문서와 dependency에 반영했다.

**반영 상세**:
- `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main`으로 upstream `main` 최신 commit `1a28b1099ab6c9c03e892e469974aee8c07deda1`을 확인했다.
- `kor-travel-geo-ui/package.json`과 `package-lock.json`의 `maplibre-vworld` dependency를 최신 확인 SHA로 갱신했다. CI에서 SSH key 없이 설치되도록 dependency와 lockfile `resolved`는 `git+https` 형식을 유지한다.
- ADR-032를 추가했다. VWorld layer/style, marker/popup/cluster primitive, tile error redaction, package export/type/CSS처럼 범용 기능은 `digitie/maplibre-vworld-js`에서 보강하고, geocode/reverse 입력 연결, API 응답 overlay, 정합성/성능/적재 상태 표시, 이 프로젝트 fallback UX는 `kor-travel-geo-ui` domain wrapper에서 구현한다.
- `README.md`, `docs/architecture.md`, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/tasks.md`, `docs/resume.md`, `docs/t036-maplibre-vworld-sync.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `maplibre-vworld` dependency를 건드리는 PR은 최신 `main` 또는 stable release 확인 결과를 남긴다.
- upstream에 보낼 것은 범용 VWorld/MapLibre 기능이며, 주소 지오코딩 디버그/관리 UI에만 의미가 있는 기능은 이 저장소에서 구현한다.
- SHA 갱신 후에는 `kor-travel-geo-ui`에서 `npm ci`, lint, type-check, test, build를 재검증한다.

## 2026-05-26 (T-047 등록 — 전국 적재 후 쿼리 성능 벤치마크와 튜닝 설계)

**작업**: 사용자 지시에 따라 전국 전체 적재 이후 지오코딩/역지오코딩/검색 쿼리 속도를 다수 반복 측정하고, 병목이 있으면 보조 view/materialized view까지 적극 도입하는 성능 튜닝 계획을 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-031을 추가했다. T-047은 p50/p95/p99, timeout, buffer, plan, 동시성 결과를 운영 준비 gate로 둔다.
- `docs/t047-query-performance-tuning.md`를 추가했다. benchmark corpus, 측정 방법, 초기 latency 목표, 튜닝 루프, 최소 실험 수, 보조 view/MV 후보, 산출물 구조, 후속 PR 순서를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`, `README.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- 속도는 정합성 이후 별도 gate로 관리한다. 전국 DB에서 목표를 초과하는 query군은 반드시 후보 실험을 수행한다.
- 보조 view/MV는 source of truth가 아니라 master table 또는 `mv_geocode_target`에서 재생성 가능한 read-only serving accelerator로만 허용한다.
- 튜닝 PR은 변경 전/후 p95/p99, plan, buffer, full-load/MV refresh/backup 부작용을 함께 기록해야 한다.

## 2026-05-26 (T-046 등록 — 적재 완료 DB 백업/복원 설계)

**작업**: 사용자 지시에 따라 완전히 적재한 PostgreSQL/PostGIS DB를 압축 artifact로 백업하고 새 DB로 복원하는 운영 설계를 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-030을 추가했다. 대용량 운영 기본값은 plain SQL/DDL dump가 아니라 `pg_dump -Fd --jobs` directory dump와 `tar.zst` 압축 아카이브다.
- `docs/t046-db-backup-restore.md`를 추가했다. 백업 profile, manifest, checksum, callback, 진행률 phase, 복원 안전장치, `/admin/backups` UI, 취소/실패 처리, 보안 allowlist를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/agent-guide.md`, `README.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `db_backup`과 `db_restore`는 백그라운드 job으로 실행하고, 상태 조회·취소·SSE는 중립 `/v1/admin/jobs/*` 표면을 우선 사용한다.
- 백업 파일은 브라우저 로컬 경로가 아니라 서버 allowlist 하위 경로에 저장한다. UI 다운로드 링크는 완료 artifact를 로컬로 받기 위한 부가 경로다.
- 구현 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB `kor_travel_geo_t046_daegu` → `kor_travel_geo_t046_daegu_restore` backup/restore로 먼저 수행한다.

## 2026-05-26 (T-045 등록 — source set 기준월 선택과 업로드/적재 UX)

**작업**: 사용자 지시에 따라 원천 자료별 기준월이 다를 수 있음을 전제로 한 적재 UX와 API/CLI 함수 분리 설계를 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-029를 추가했다. 원천 묶음은 단일 `yyyymm`이 아니라 `source_set.yyyymm_by_kind`로 기록하고, 혼합 기준월은 사용자 확인을 거쳐야 한다.
- `docs/t045-source-set-load-ux.md`를 추가했다. CLI 대화형 확인, 비대화형 confirmation token, `discover_load_sources()`와 `build_full_load_source_set_plan()` 함수 분리, upload set API, UI 다중 파일/DND 업로드, 업로드/적재 진행률과 취소 UX를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- API/라이브러리는 사용자 prompt를 띄우지 않고 발견/계획/등록을 분리한다.
- CLI와 UI는 기준월 mismatch를 사용자에게 표로 보여 주고, 명시 확인 없이는 적재를 시작하지 않는다.
- 업로드는 DB 적재와 분리한다. 모든 파일 저장과 checksum/기준월 분석이 끝난 뒤에만 `full_load_batch`를 등록한다.

## 2026-05-26 (T-044 등록 — `maplibre-vworld-js` 완전 포팅)

**작업**: 사용자 지시에 따라 디버그 UI를 `maplibre-vworld-js`로 완전히 포팅하는 작업을 백로그와 ADR에 추가했다.

**반영 상세**:
- `docs/tasks.md`에 T-044를 추가했다. 범위는 `CoordinateMap.tsx`의 직접 MapLibre wiring을 upstream `VWorldMap` 또는 동등한 Hook/component로 대체하는 것이다.
- ADR-028을 추가했다. 부족한 click callback, marker 제어, `flyToOptions`, tile error hook/redaction, key 미설정 fallback, SSR-safe 사용법, 타입/패키징 문제는 `kor-travel-geo`에서 우회하지 않고 `digitie/maplibre-vworld-js`를 직접 수정한다.
- `docs/frontend-package.md`, `docs/architecture.md`, `docs/t036-maplibre-vworld-sync.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- T-044는 두 저장소 작업으로 본다. 필요한 upstream 보강은 `maplibre-vworld-js` PR/commit으로 남기고, 그 검증된 SHA를 `kor-travel-geo-ui` dependency로 소비한다.
- 완료 조건에는 upstream test/build와 `kor-travel-geo-ui`의 `npm ci`, lint, type-check, test, build 검증을 포함한다.

## 2026-05-26 (T-043 등록 — PR #23~#33 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #23부터 최신 PR #33까지의 리뷰 코멘트를 다시 읽고 반영하는 후속 작업을 백로그에 추가했다.

**반영 상세**:
- `docs/tasks.md` 대기 목록 최상단에 T-043을 추가했다.
- 대상 범위는 PR #23~#33이다. PR #33은 먼저 main에 merge한 뒤 이 작업을 등록했다.
- 확인 표면은 `comments`, `reviews`, `latestReviews`, pull request review comments, GraphQL `reviewThreads`를 모두 포함한다.
- 완료 산출물은 `docs/postmerge-review-fixups-pr23-pr33.md`로 지정했다.
- `docs/resume.md`의 다음 작업을 T-043으로 갱신했다.

**다음 작업**: T-043을 실제로 수행할 때 PR별 코멘트/스레드 표를 만들고, 반영 가능한 변경은 후속 fixup PR로 올린다.

## 2026-05-26 (T-041 후속 — `TL_SPPN_MAKAREA` 문서 보강)

**작업**: 사용자 설명을 반영해 `TL_SPPN_MAKAREA`를 단순 overlay 후보가 아니라 국가지점번호 표기 의무지역 polygon으로 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- `docs/t041-detail-zone-shape-layers.md`에 `TL_SPPN_MAKAREA`의 네이밍(`SPPN`, `MAKAREA`), 업무 의미, 지점번호표기 의무지역 개념, geocode/reverse geocode 활용 방식을 상세히 추가했다.
- ADR-027을 추가했다. `TL_SPPN_MAKAREA`는 `mv_geocode_target`에 union하지 않고, 후속 `tl_sppn_makarea` 별도 테이블과 `x_extension.sppn_makarea` 또는 `type='sppn_area'` 후보로 노출한다.
- `docs/data-model.md`, `docs/backend-package.md`, `docs/t030-extra-shape-sources.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `TL_SPPN_MAKAREA`는 개별 국가지점번호판 point 목록이 아니라 표기 의무지역 polygon이다.
- geocode는 국가지점번호 문자열 parser/generator가 좌표를 계산한 뒤 해당 좌표가 의무지역에 속하는지 검증하는 enrichment로 사용한다.
- reverse geocode는 도로명/지번 주소 후보가 없거나 confidence가 낮은 비거주지역에서 `ST_Covers` 기반 보조 후보로 사용한다.
- 구현 후속 작업은 T-042로 등록했다.

**검증**:
- 문서 변경만 수행했다. `git diff --check`로 whitespace를 확인한다.

## 2026-05-26 (T-037 — SHP geometry 포함 대형 레이어 적재 튜닝)

**작업**: PR #31 merge 이후 `codex/t037-shp-geometry-tuning` 브랜치에서 `TL_SPBD_BULD` 직접 GDAL append 병목을 projection staging table 경로로 보강했다.

**반영 상세**:
- `src/kortravelgeo/loaders/shp/polygons_loader.py`에서 `TL_SPBD_BULD`만 `_ktg_stage_spbd_buld_polygon` staging table로 분기한다.
- staging 생성은 `accessMode="overwrite"`, `PG_USE_COPY=YES`, `SHAPE_ENCODING=CP949`, 기존 `plan.sql_statement` projection을 함께 사용한다.
- 운영 테이블 insert는 `SET LOCAL search_path = public, x_extension` 후 `INSERT ... SELECT`로 수행하고, `ST_Multi(geom)::geometry(MultiPolygon, 5179)`와 문자열 trim/NULL 정규화, 건물번호 integer cast를 명시했다.
- staging table은 시작 전과 종료 `finally`에서 모두 drop한다.
- `docs/t037-shp-geometry-tuning.md`를 추가하고 `docs/backend-package.md`, `docs/t034-shp-append-tuning.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**실제 파일 검증**:
- 세종 단일 `TL_SPBD_BULD`: 기존 append 38.36초 → projection staging 18.59초, 55,819행, source 추적 컬럼 전량 채움, staging table 없음.
- 경기도 raw staging은 원본 DBF 전체 속성을 복사해 22분 58.46초 동안 끝나지 않아 `pg_terminate_backend()`로 중단했다. 중단 지점은 GDAL feature 617,214 부근이었다.
- 경기도 projection staging: 1,649,975행, 40분 17.15초, source 추적 컬럼 전량 채움, staging table 없음.
- 세종 public CLI `ktgctl load shp ... --mode full --yyyymm 202604`: 9개 레이어 적재 성공, 1분 19.54초, `tl_spbd_buld_polygon=55,819`, `tl_sprd_intrvl=100,009`, `tl_sprd_rw=7,429`.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q` → 17 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo/loaders/shp/polygons_loader.py` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없거나 반영이 끝나면 main에 merge하고 T-027 최종 실 데이터 클린 적재 검증으로 진행한다.

## 2026-05-26 (T-041 — 상세주소 동 도형/구역 추가 레이어 검토)

**작업**: PR #30 merge 이후 `codex/t041-extra-shape-layer-review` 브랜치에서 `건물군 내 상세주소 동 도형`과 `구역의 도형`을 실제 세종/경남 파일로 전자지도와 비교했다.

**반영 상세**:
- `src/kortravelgeo/loaders/shape_dbf.py`를 추가해 DBF/SHP layer summary와 key set overlap helper를 공용화했다.
- T-040 `building_shape_bundle.py`는 공용 helper를 사용하도록 정리했다.
- `src/kortravelgeo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`를 추가했다.
- ADR-026을 추가했다. 상세주소 동 도형과 구역 추가 레이어는 기본 `full_load_batch`/`mv_geocode_target`에 섞지 않고, 필요 시 별도 overlay/분석 테이블로 둔다.

**실제 파일 검증**:
- 세종 상세주소 동 polygon은 40,478행이고 전자지도 `TL_SPBD_BULD` 55,819행의 부분집합이었다. `BD_MGT_SN + EQB_MAN_SN` 교집합은 40,478, detail only 0, 전자지도 only 15,341이다.
- 경남 상세주소 동 polygon은 923,702행이고 전자지도 `TL_SPBD_BULD` 1,269,029행의 부분집합이었다. 교집합은 923,702, detail only 0, 전자지도 only 345,327이다.
- 세종 `구역의 도형` 중 `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`는 전자지도와 key 기준 완전 중복이었다. 경남도 같은 결과다.
- `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key 교집합이 0건이고, `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key였다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_building_shape_bundle.py tests/unit/test_extra_shape_layers.py tests/integration/test_real_extra_shape_sources.py -q` → 11 passed, 2 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_SLOW_REAL_DATA=1 .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q` → 1 passed in 16.74s.
- `scripts/compare_extra_shape_layers.py`로 세종 실제 파일 JSON 출력을 확인했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 148 passed, 5 skipped.
- `ruff check .`, `mypy src/kortravelgeo scripts/compare_extra_shape_layers.py scripts/compare_building_shape_bundle.py`, `lint-imports`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없으면 main에 merge하고 T-037 geometry 포함 SHP 대형 레이어 적재 튜닝으로 진행한다.

## 2026-05-26 (T-040 — `도로명주소 건물 도형` bundle 비교)

**작업**: PR #29 merge 이후 `codex/t040-building-shape-bundle` 브랜치에서 `도로명주소 건물 도형` bundle과 기존 전자지도 건물/출입구 레이어의 natural key overlap을 실제 파일로 비교했다.

**반영 상세**:
- `src/kortravelgeo/loaders/building_shape_bundle.py`를 추가했다. ZIP 내부 `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC`와 전자지도 `TL_SPBD_BULD`, `TL_SPBD_ENTRC`의 DBF key set을 순수 Python으로 비교한다.
- `scripts/compare_building_shape_bundle.py`를 추가해 세종/경남 비교 결과를 JSON으로 재현할 수 있게 했다.
- ADR-025를 추가했다. `도로명주소 건물 도형`은 단순 중복이 아니지만 현행 `tl_spbd_buld_polygon`/serving MV에는 섞지 않고, 후속 loader가 필요하면 `tl_roadaddr_buld_polygon`, `tl_roadaddr_buld_entrc`, `tl_roadaddr_spot_cntc` 같은 별도 테이블로 둔다.
- 세종 실제 비교는 기본 integration test로 넣고, 경남 full key scan은 `KTG_SLOW_REAL_DATA=1` 선택 테스트로 분리했다.

**실제 파일 검증**:
- 세종 address polygon key: bundle 27,792 distinct, 전자지도 `TL_SPBD_BULD` 55,819 distinct, 교집합 15,339, bundle only 12,453, 전자지도 only 40,480.
- 경남 address polygon key: bundle 656,230 distinct, 전자지도 `TL_SPBD_BULD` 1,269,029 distinct, 교집합 345,290, bundle only 310,940, 전자지도 only 923,739.
- 세종 출입구 key: bundle 28,111, 전자지도 27,787, 교집합 27,766, bundle only 345, 전자지도 only 21.
- 경남 출입구 key: bundle 661,416, 전자지도 656,133, 교집합 656,114, bundle only 5,302, 전자지도 only 19.

**검증**:
- `python -m pytest tests/unit/test_building_shape_bundle.py tests/integration/test_real_extra_shape_sources.py -q` → 7 passed, 1 skipped.
- `KTG_SLOW_REAL_DATA=1 python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_building_shape_bundle_gyeongnam_key_overlap_slow -q` → 1 passed in 18.48s.
- `python -m pytest -q` → 144 passed, 4 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` → 통과.

## 2026-05-26 (T-039 — PR 전 검증 보강)

**작업**: T-039 PR 생성 전 전체 검증을 돌리며 문서/DDL/테스트 계약을 보강했다.

**반영 상세**:
- 기본 DDL 문자열(`sql/ddl/001_schema.sql`, `infra/sql.py`)에서 `tl_roadaddr_entrc.ent_man_no`를 Alembic 0005와 동일하게 nullable로 맞췄다. 반대로 기존 `tl_locsum_entrc.ent_man_no`는 `sig_cd + ent_man_no` PK이므로 `NOT NULL`을 유지한다.
- `tests/unit/test_consistency_sql.py`는 T-039의 `serving_entrc` CTE와 `source_kind` sample을 검증하도록 갱신했다.
- `docs/backend-package.md`, `docs/t039-roadaddr-entrance-loader.md`, `README.md`에 T-039 이전 MV가 있는 DB에서는 direct 출입구 적재 뒤 `ktgctl refresh mv --swap`을 권장한다고 명시했다.

**검증**:
- `python -m pytest -q` → 141 passed, 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check --output openapi.json`, `git diff --check` → 통과.
- Docker PostGIS `localhost:15432`의 새 `kor_travel_geo_t039` DB에서 `tests/integration/test_optional_real_postgres_load.py` → 1 passed in 2.86s.
- `kor-travel-geo-ui`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

## 2026-05-26 (T-039 — `도로명주소 출입구 정보` direct entrance loader)

**작업**: PR #28 merge 이후 `codex/t039-direct-entrance-loader` 브랜치에서 `RNENTDATA_2605_*.txt` direct entrance 원천을 적재하는 T-039를 구현했다.

**반영 상세**:
- `tl_roadaddr_entrc` 테이블과 Alembic `0005_t039_roadaddr_entrance_table`을 추가했다. 실제 파일에서 `ent_man_no`가 비는 행이 있어 PK는 `bd_mgt_sn` 단독으로 두고, `ent_man_no`는 nullable 원천 보존 필드로 둔다.
- `src/kortravelgeo/loaders/text/roadaddr_entrance_loader.py`를 추가했다. 디렉터리 입력 시 17개 ZIP 내부의 `RNENTDATA_*.txt` member를 직접 발견하고, 좌표 결측/`0/0` sentinel row는 skip한다.
- CLI `ktgctl load roadaddr-entrances`와 API job kind `roadaddr_entrance_load`를 추가했다.
- `mv_geocode_target` 대표 좌표 선택 순서를 `tl_roadaddr_entrc` → `tl_locsum_entrc` → `tl_navi_buld_centroid`로 바꿨다. 응답 호환성을 위해 direct entrance도 기존 `pt_source='entrance'`로 둔다.
- C3/C4/C6/C7/C8 정합성 SQL은 `tl_roadaddr_entrc`와 `tl_locsum_entrc`를 합친 대표 출입구 CTE를 사용하게 했고, C10 기준월 비교에 `tl_roadaddr_entrc`를 포함했다.

**실제 파일/DB 검증**:
- 전국 17개 ZIP을 직접 읽어 총 6,418,169행, 모든 행 19컬럼, `ent_source_cd='RM'`, `ent_detail_cd='01'`을 확인했다.
- 세종 ZIP은 원천 27,868행, distinct `bd_mgt_sn` 27,868, 빈 `ent_man_no` 9건, 유효 좌표 적재 대상 27,779행이었다.
- 경남 ZIP은 원천 657,845행, distinct `bd_mgt_sn` 657,845, 빈 `ent_man_no` 100건이었다.
- Docker PostGIS `localhost:15432`에 `kor_travel_geo_t039` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.74s`이며 세종 RNENTDATA 3행이 `tl_roadaddr_entrc`와 `load_manifest`에 반영됐고, MV의 `pt_5179`가 direct entrance 좌표를 사용함을 확인했다.
- 대상 테스트 `tests/unit/test_roadaddr_entrance_loader.py`, `tests/integration/test_real_roadaddr_entrance_files.py`, schema/batch/CLI 계약 테스트 → 29 passed.
- 대상 `ruff check`와 `mypy src/kortravelgeo` → 통과.

**다음 작업**: 전체 검증과 frontend/OpenAPI drift 확인 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-038 — `tl_juso_parcel_link` DDL/로더 구현)

**작업**: PR #27 merge 이후 `codex/t038-parcel-link-loader` 브랜치에서 ADR-022의 보조 지번 1:N 테이블을 실제 구현했다.

**반영 상세**:
- `tl_juso_parcel_link` 테이블, 인덱스 3종, Alembic `0004_t038_parcel_link_table`을 추가했다. `bd_mgt_sn`은 `tl_juso_text` FK + `ON DELETE CASCADE`, PK는 `(bd_mgt_sn, pnu)`다.
- `src/kortravelgeo/loaders/text/parcel_link_loader.py`를 추가했다. `jibun_rnaddrkor_*` full snapshot은 기본 `TRUNCATE` 후 UPSERT하고, daily `LNBR`은 `MVM_RES_CD` mapping에 따라 UPSERT/DELETE한다.
- CLI `ktgctl load parcel-links`, `ktgctl load daily-parcel-links`를 추가했다.
- API job kind `juso_parcel_link_load`, `juso_parcel_link_delta`를 추가했고, `full_load_batch` 기본 child 순서에 `juso_text_load` 직후 `juso_parcel_link_load`를 넣었다.
- `kor-travel-geo-ui` `/admin/load` 기본 payload에도 `juso_parcel_link_load`를 추가했다.
- `daily_juso_delta`는 MST 전용으로 유지하고, 같은 ZIP의 LNBR은 `juso_parcel_link_delta`로 별도 적용한다.

**실제 파일/DB 검증**:
- 실제 `jibun_rnaddrkor_seoul.txt`를 새 iterator로 파싱해 PNU `1111012000101500000`, `1114010300100680000`을 확인했다.
- 실제 `20260401_dailyjusukrdata.zip`의 LNBR 204행을 새 iterator로 파싱하고 첫 행 PNU `4148025326100310007`, `mvmn_de=20260402`, `MVM_RES_CD=31`을 확인했다.
- Docker PostGIS `localhost:15432`에 `kor_travel_geo_t038` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.81s`이며 snapshot 2행, daily LNBR 5행이 `tl_juso_parcel_link`와 `load_manifest`에 반영됐다.
- 전체 `pytest -q` → 133 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
- frontend `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기한다. 리뷰 코멘트가 있으면 최대한 반영하고, 없으면 main에 merge한 뒤 T-039로 진행한다.

## 2026-05-26 (T-030 — 별도 도형/출입구 자료 검토)

**작업**: PR #26 merge 이후 `codex/t030-extra-shape-sources` 브랜치에서 별도 도형/출입구 ZIP 4종을 실제 세종특별자치시 파일로 확인했다.

**실제 파일 확인**:
- `건물군내동도형_전체분_세종특별자치시.zip`: `TL_SGCO_RNADR_DONG` Polygon 40,478행, `TL_SPBD_ENTRC_DONG` Point 4,098행.
- `구역의도형_전체분_세종특별자치시.zip`: 기존 전자지도와 중복되는 `TL_SCCO_*`, `TL_KODIS_BAS` 외에 `TL_SCCO_GEMD` 24행, `TL_SPPN_MAKAREA` 146행이 있다.
- `건물도형_전체분_세종특별자치시.zip`: `TL_SGCO_RNADR_MST` Polygon 27,792행, `TL_SPBD_ENTRC` Point 28,111행, `TL_SPOT_CNTC` PolyLine 27,776행.
- `도로명주소출입구_전체분_세종특별자치시.zip`: `RNENTDATA_2605_36110.txt` 19컬럼 텍스트이며 direct `bd_mgt_sn`, 도로명주소 키, 출입구 관리번호, EPSG:5179 X/Y를 제공한다.

**결정**:
- 네 자료를 현재 full-load 기본 source child에는 즉시 추가하지 않는다.
- `도로명주소 출입구 정보`는 direct `bd_mgt_sn + 5179 point`라 T-039 후보로 둔다.
- `도로명주소 건물 도형`은 전자지도 `TL_SPBD_BULD` 단순 중복이 아니므로 T-040에서 bundle 비교를 진행한다.
- 상세주소 동 도형과 구역 추가 레이어는 T-041에서 디버그 UI/상세주소/품질 분석 용도를 따로 검토한다.
- ADR-023과 `docs/t030-extra-shape-sources.md`에 근거와 후속 순서를 기록했다.

**검증 진행**:
- `pytest tests/integration/test_real_extra_shape_sources.py -q` → 4 passed.
- `pytest -q` → 128 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-029 — `jibun_rnaddrkor_*` 활용 결정)

**작업**: PR #25 merge 이후 `codex/t029-jibun-rnaddrkor-decision` 브랜치에서 `jibun_rnaddrkor_*`와 daily `TH_SGCO_RNADR_LNBR.TXT`의 실제 구조와 cardinality를 확인했다.

**실제 파일 확인**:
- `jibun_rnaddrkor_seoul.txt` 첫 행은 14컬럼이며, daily `LNBR`도 같은 14컬럼 구조를 쓰되 마지막 컬럼에 `MVM_RES_CD`가 들어간다.
- 전국 `jibun_rnaddrkor_*`: 1,769,370행, distinct `bd_mgt_sn` 986,309, 2개 이상 보조 지번을 가진 건물 334,789건, 한 건물 최대 545행.
- 서울 `jibun_rnaddrkor_seoul.txt`: 89,290행, distinct `bd_mgt_sn` 52,280, 2개 이상 보조 지번을 가진 건물 13,318건.
- 서울 `jibun_rnaddrkor` PNU와 `rnaddrkor` 대표 PNU 비교: 89,290행 중 89,289행이 대표 PNU와 다르고, `rnaddrkor`에서 찾지 못한 `bd_mgt_sn`은 0건이었다.
- daily `20260401` LNBR: 204행, distinct `bd_mgt_sn` 72, 2개 이상 변경 지번을 가진 건물 31건, 코드 분포 `31=74`, `63=130`.

**결정**:
- `jibun_rnaddrkor_*`와 daily `LNBR`는 `tl_juso_text.pnu`에 덮어쓰지 않는다.
- 후속 T-038에서 `tl_juso_parcel_link` 별도 1:N 테이블을 도입한다.
- `mv_geocode_target`은 계속 `bd_mgt_sn` unique를 유지하고, 보조 지번은 지번 검색 후보 확장/디버그 표시/정합성 검증에 단계적으로 연결한다.
- ADR-022와 `docs/t029-jibun-rnaddrkor-decision.md`에 근거와 테이블 초안을 기록했다.

**검증 진행**:
- `pytest tests/integration/test_real_jibun_rnaddrkor_files.py -q` → 2 passed.
- 전체 `pytest -q` → 124 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-028 — 도로명주소 일변동 ZIP 로더)

**작업**: PR #24 merge 이후 `codex/t028-daily-delta-loader` 브랜치에서 `data/juso/daily/*.zip` 일변동 ZIP 로더를 구현했다.

**반영 상세**:
- `src/kortravelgeo/loaders/text/daily_juso_loader.py`를 추가했다. `AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT`를 읽어 `tl_juso_text`에 UPSERT/DELETE로 반영한다.
- `MVM_RES_CD`는 `Settings.mvm_res_code_actions`를 사용한다. 기본값은 `31/33=insert`, `34/35/36=update`, `63/64=delete`이며, 알 수 없는 코드는 `LoaderError`로 중단한다.
- 한 batch 안의 동일 `bd_mgt_sn`은 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 master에 반영한다.
- `TH_SGCO_RNADR_LNBR.TXT`는 현재 master table에 쓰지 않고 `unsupported_lnbr_rows`로 집계해 `load_manifest.source_set`에 남긴다. T-029에서 `jibun_rnaddrkor_*`와 함께 1:N 지번 관계 테이블 여부를 결정한다.
- member 내용이 `No Data`인 경우 컬럼 수 오류로 보지 않고 skip하며 `skipped_no_data_sources`에 기록한다.
- CLI `ktgctl load daily-juso`와 API job kind `daily_juso_delta`를 추가했고, `openapi.json` 및 `kor-travel-geo-ui/types/api.gen.ts`를 갱신했다.
- ADR-021과 `docs/t028-daily-juso-delta.md`를 추가해 MST/LNBR 분리, manifest watermark, 실제 파일 검증 수치를 문서화했다.

**실제 파일 확인**:
- `/mnt/f/dev/kor-travel-geo/data/juso/daily/20260401_dailyjusukrdata.zip`의 MST member는 422행이며 코드 분포는 `31=185`, `34=57`, `63=180`이었다.
- 같은 ZIP의 LNBR member는 204행이며 이번 구현에서는 manifest에 미지원 행 수로만 기록한다.
- `/mnt/f/dev/kor-travel-geo/data/juso/daily/20260404_dailyjusukrdata.zip`은 MST/LNBR 모두 `No Data`였다.

**검증 진행**:
- `pytest tests/unit/test_daily_juso_loader.py tests/integration/test_real_juso_text_loaders.py::test_actual_daily_juso_zip_loads_mst_rows_and_skips_no_data_members tests/unit/test_cli_contract.py -q` → 11 passed.
- `pytest tests/integration/test_real_juso_text_loaders.py -q` → 실제 NTFS `data/juso` fallback으로 5 passed.
- Docker PostGIS `localhost:15432`에 전용 DB `kor_travel_geo_t028`을 생성하고 `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t028 pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 이 검증은 daily sample 3행 적용 뒤 `load_manifest.last_mvmn_de=20260402`, `row_count=3`, `unsupported_lnbr_rows=204`까지 확인한다.
- 대상 `ruff check`와 대상 `mypy` → 통과.
- `scripts/export_openapi.py`와 frontend `npm run gen:types` 실행.
- 전체 `pytest -q` → 122 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
- frontend `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

**다음 작업**: 전체 검증과 실제 PostgreSQL sample daily load를 실행한 뒤 PR을 열어 리뷰 대기한다.

## 2026-05-26 (PR #20~#22 post-merge 리뷰 반영)

**작업**: T-036 PR #23이 main에 merge된 뒤, 사용자 지시 순서대로 PR #22 → PR #21 → PR #20 리뷰 코멘트를 thread-aware 방식으로 확인했다. 세 PR 모두 merged 상태였고 conversation comment 1개씩만 있었으며 formal review와 inline review thread는 없었다.

**PR #22 반영**:
- `postload.rename_mv_next_indexes_for_conn(conn)` public helper를 추가해 benchmark script가 `_rename_mv_next_indexes` private helper를 직접 import하지 않게 했다.
- `scripts/benchmark_mv_refresh.py`에 `schema_version=2`, `metadata`(`trial_index`, `cache_warm_hint`, `notes`, active session 수, wait event snapshot)를 추가했다.
- `_optional_int()`는 `ProgrammingError`만 잡고 rollback한 뒤 `None`을 반환한다.
- benchmark와 production `shadow_swap_mv()`의 `ANALYZE` transaction에도 `SET LOCAL lock_timeout = '2s'`를 적용했다.
- `docs/data-model.md` shadow swap 예시는 실제 `idx_mv_next_*` → `idx_mv_*` index rename 단계를 보여주도록 보강했다.

**PR #21 반영**:
- `TL_SPRD_INTRVL` COPY row를 `RoadIntervalRow` dataclass로 묶고, `ROAD_INTERVAL_COPY_COLUMNS`와 tuple shape를 같은 코드 표면에 둔다.
- CP949 decode 실패와 truncated record 오류 메시지에 파일, record, field, byte size 문맥을 포함한다.
- psycopg COPY connection은 `autocommit=False`를 명시하고 explicit commit 의도를 주석으로 남겼다.
- deleted record skip, CP949 decode error, truncated record error 단위 테스트를 추가했다.

**PR #20 반영**:
- `scripts/fullload_test.sh`에 DDL, juso, locsum, navi, SHP, link, MV, total timer를 추가했다.
- `docs/t033-full-load-revalidation.md`에 SHP 시간 출처, 단발 측정 한계, C10 `OK 0` 의미, `tl_navi_entrc` 원천 cross-check 필요성을 명시했다.
- `TL_SPBD_BULD` 등 geometry 포함 대형 SHP 튜닝을 T-037 후보로 등록했다.

**검증 진행**:
- `pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py -q` → 8 passed.
- `pytest tests/unit/test_shp_loader_gdal.py -q` → 16 passed.
- 대상 `ruff check` → 통과.
- 전체 `pytest -q` → 113 passed / 7 skipped.
- `ruff check .`, `mypy src/kortravelgeo scripts/benchmark_mv_refresh.py`, `lint-imports`, `bash -n scripts/fullload_test.sh`, `git diff --check` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후, 코멘트가 있으면 반영하고 없으면 main에 merge한다.

## 2026-05-26 (T-036 — `maplibre-vworld-js` main 동기화)

**작업**: PR #22 merge 이후 `codex/t036-maplibre-vworld-sync` 브랜치에서 `kor-travel-geo-ui`의 `maplibre-vworld` dependency를 `digitie/maplibre-vworld-js` 최신 main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신했다.

**반영 상세**:
- `kor-travel-geo-ui/package.json`과 lockfile의 `maplibre-vworld` GitHub SHA를 `11321fe8b8f4da849ee5c24ba18a27206a55e26e`에서 `c91c9f304669ce3f5fc4915f21186b23731d5816`로 올렸다. CI에서 SSH key 없이 설치되어야 하므로 dependency와 `resolved`는 모두 `git+https`를 유지한다.
- 최신 upstream은 `redactVWorldTileUrl()`가 아니라 `redactVWorldUrl()`를 export하고, redaction 표기는 `[redacted]` 대신 `***`를 사용한다.
- `kor-travel-geo-ui/lib/vworld.ts`는 `redactVWorldUrl as redactVWorldTileUrl` alias를 둬 기존 `CoordinateMap` import 계약을 유지한다.
- VWorld helper 테스트는 최신 upstream redaction 표기 `***`를 검증하도록 갱신했다.
- `docs/t036-maplibre-vworld-sync.md`에 upstream 확인 SHA, API 변경, WSL Linux Node 검증 명령, 남은 작업 순서를 기록했다.

**검증**:
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm ci --ignore-scripts` → 통과. 기존 moderate advisory 7건은 유지.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run lint` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run type-check` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run build` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 사용자 지시대로 PR #22, PR #21, PR #20 순서로 신규 리뷰 코멘트를 확인하고 반영 가능한 항목을 처리한다.

## 2026-05-26 (T-035 — MV refresh/swap 벤치마크)

**작업**: PR #21 merge 이후 `codex/t035-mv-refresh-benchmark` 브랜치에서 `mv_geocode_target` 갱신 전략을 실제 전국 DB `kor_travel_geo_t033`에서 비교했다. 재현 가능한 계측을 위해 `scripts/benchmark_mv_refresh.py`를 추가하고, `CONCURRENTLY`와 shadow swap의 phase별 시간, temp file/byte 증가, index 크기를 JSON으로 남겼다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`, DB `kor_travel_geo_t033`.
- 데이터 상태: T-033 전국 full-load 결과, `mv_geocode_target=6,416,637`, DB size 약 26GB.
- 시스템: WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, 16 logical cores, RAM 29GiB, 실행 시 available 약 27GiB.
- artifact: `artifacts/t035-mv-refresh-20260526_045339/` (git ignore).

**측정 결과**:
- `CONCURRENTLY`: `/usr/bin/time` wall clock 1분 49.64초. phase는 `refresh_concurrently=106.68초`, `analyze=4.96초`. temp는 +91 files, +12,309,605,099 bytes. 실행 중 `BufFileWrite` I/O wait가 관측됐다.
- `swap`: `/usr/bin/time` wall clock 2분 16.28초. `rebuild.create_next=68.79초`, index build 합계 약 63.29초, `swap.analyze_live=4.89초`. temp는 +44 files, +9,150,995,144 bytes.
- swap의 rename/index rename 구간(`drop_old_pre`, `rename_live_to_old`, `rename_next_to_live`, `drop_old_post`, `rename_indexes`) 합계는 약 0.016초였다.

**반영 상세**:
- `scripts/benchmark_mv_refresh.py`는 `--strategy concurrent|swap`와 `--output`을 받아 phase별 JSON을 출력한다.
- `postload.build_mv_next_sql()`을 공개 helper로 분리해 실제 swap SQL과 benchmark script가 같은 SQL 생성 경로를 공유한다.
- 기존 `shadow_swap_mv()`가 rename/drop 이후 `ANALYZE`까지 같은 transaction에서 실행하던 점을 확인하고, rename transaction과 `ANALYZE` transaction을 분리했다. 이로써 swap lock-sensitive 구간에 약 4.9초짜리 통계 갱신을 포함하지 않는다.
- 최종 검증에서 `mv_geocode_target_next`, `mv_geocode_target_old`는 남지 않았고, 운영 index 이름은 `idx_mv_*`로 정상 정규화됐다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py -q` → 8 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check scripts/benchmark_mv_refresh.py tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py src/kortravelgeo/loaders/postload.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy scripts/benchmark_mv_refresh.py src/kortravelgeo/loaders/postload.py` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-036에서 `maplibre-vworld-js` upstream main과 UI dependency를 동기화한다.

## 2026-05-26 (T-034 — SHP append 병목 튜닝)

**작업**: PR #20 merge 이후 `codex/t034-shp-append-tuning` 브랜치에서 T-033의 최우선 병목이었던 `TL_SPRD_INTRVL` 적재 경로를 보강했다. geometry가 없는 DBF 속성 레이어는 GDAL `VectorTranslate` append를 우회해 직접 DBF scan + `psycopg COPY`로 적재하도록 분기했다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`.
- 데이터: ext4 mirror `/home/digitie/kor-travel-geo-data/juso/도로명주소 전자지도`.
- 시스템: WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, 16 logical cores, RAM 29GiB, 실행 시 available 약 27GiB.
- 디스크: ext4 `/dev/sdd` 1007G 중 758G available, NTFS `/mnt/f` 932G 중 267G available.

**반영 상세**:
- `polygons_loader._load_plans_sync()`에서 `TL_SPRD_INTRVL`만 `_copy_road_interval_dbf()`로 라우팅한다.
- DBF parser는 `SIG_CD`, `RDS_MAN_NO`, `BSI_INT_SN`, `ODD_BSI_MN`, `EVE_BSI_MN`만 추출하고, 기존 추적 컬럼 `source_file`, `source_yyyymm`을 유지한다.
- 도형 레이어(`TL_SPBD_BULD`, `TL_SPRD_RW`, 행정경계 등)는 기존 GDAL 경로를 그대로 사용한다.
- synthetic DBF unit test를 추가해 필드 순서, 숫자 필드 공백 trim, 빈 값 `None` 처리, COPY row projection을 고정했다.

**측정 결과**:
- 세종 `TL_SPRD_INTRVL` 100,009행 단일 레이어: 기존 GDAL 경로 36.12초 → 새 COPY 경로 1.59초.
- 경기도 `TL_SPRD_INTRVL` 2,677,715행 단일 레이어: 새 COPY 경로 15.88초. T-033 관찰상 기존 경기도 레이어는 약 24분 이상이었다.
- 세종 9개 SHP 레이어 전체 CLI 적재: 31.69초, `tl_sprd_intrvl=100,009`, `tl_spbd_buld_polygon=55,819`, `tl_sprd_rw=7,429`.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q` → 12 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- 실제 Docker DB `kor_travel_geo_t034_before`, `kor_travel_geo_t034_after`, `kor_travel_geo_t034_sejong`에서 기준선/개선 후/9개 레이어 전체 적재를 확인했다.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-035에서 MV refresh/swap benchmark를 진행한다. `TL_SPBD_BULD` GDAL append 병목은 도형 포함 대형 레이어라 이번 PR에서는 유지하고, 별도 튜닝 후보로 남긴다.

## 2026-05-26 (T-033 — 전국 full-load 성능 재검증)

**작업**: PR #19 merge 이후 `codex/t033-full-load-revalidation` 브랜치에서 빈 Docker DB `kor_travel_geo_t033`를 만들고 실제 전국 `data/juso` full-load를 다시 실행했다. 사용자 지시에 따라 로그와 시스템 상태를 상세히 남기고, T-034/T-035 튜닝 전 기준선으로 문서화했다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`, DB `kor_travel_geo_t033`.
- 데이터: ext4 mirror `/home/digitie/kor-travel-geo-data`, 원본 `/mnt/f/dev/kor-travel-geo/data/juso`.
- 로그: `artifacts/t033-full-load-20260525_224643/` (git ignore).

**결과**:
- full-load 전체 wall clock 4시간 8분 2초, 최대 RSS 187,964KB, exit status 0.
- 텍스트 3종은 1,098초에 완료했다. `tl_juso_text=6,416,637`, `tl_locsum_entrc=6,405,091`, `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`.
- SHP 17개 시도 × 9개 레이어 총 153 layers를 완료했다. `tl_sprd_intrvl=16,993,167`, `tl_sprd_rw=1,482,679`, `tl_spbd_buld_polygon=10,687,732`.
- `resolve_text_geometry_links()`는 약 2분 32초, `refresh mv --swap`은 약 2분 28초에 완료했다. `mv_geocode_target=6,416,637`.
- Smoke test는 geocode/reverse/search/zipcode 모두 `OK`.
- C1~C10 정합성은 `severity_max=ERROR`로 완료했다. 기존 실제 데이터 품질 이슈인 C2 34,699건, C4 over_500m 16건, C6 803건, C7 6,817건이 재현됐다.
- C2/C4/C6/C7 data-quality CSV 8개를 1분 20.41초에 export했다.

**관찰**:
- `TL_SPRD_INTRVL`은 geometry 없는 interval 테이블인데도 GDAL `VectorTranslate` 경로에서 `INSERT INTO "tl_sprd_intrvl" ... VALUES ...`로 관측됐다. 경기도 interval 단일 레이어가 약 24분 이상 걸려 T-034의 최우선 튜닝 대상이다.
- `TL_SPBD_BULD`도 batch INSERT 형태로 관측됐다. geometry 포함 대형 레이어라 비용은 예상되지만 COPY 적용 여부 확인이 필요하다.
- SHP 적재 중 DB CPU는 대체로 30~50%, 메모리는 4~9GiB 수준이었다. C4/C5 정합성 검증에서는 메모리가 약 14GiB까지 올라갔다.
- `TL_SPRD_RW`, `TL_SPBD_BULD`, 일부 행정경계 SHP에서 winding order 자동 보정 경고가 반복됐지만 적재는 계속 진행됐다.

**다음 작업**: PR #20으로 T-033 문서 PR을 열고 20분 리뷰 대기 후, 코멘트 반영 또는 무코멘트면 main에 merge한다. 이후 T-034에서 `TL_SPRD_INTRVL` 전용 COPY 로더 또는 GDAL 옵션 분리 튜닝을 진행한다.

## 2026-05-25 (PR #19 리뷰 반영 — T-032 머지 전 보강)

**작업**: PR #19 formal review를 확인하고 머지 권장 조건(M1, M3+L1, L9)과 즉시 처리 가능한 Low 항목을 반영했다.

**반영 상세**:
- `export_data_quality_samples()`는 prepare temp table 생성과 export query를 명시적 `async with conn.begin()` 안에서 실행한다. DB transaction 뒤에 CSV를 쓰도록 해 `ON COMMIT DROP` temp table 계약과 lock 시간을 분리했다.
- `data_quality`의 로컬 SQL splitter를 제거하고 `infra.sql.iter_sql_statements()`로 통합했다. 공용 splitter는 string literal, quoted identifier, comment, dollar quote 안의 세미콜론을 보존한다.
- `resolve_text_geometry_links()`는 기본 30분 transaction-local timeout 의도를 docstring으로 설명하고, `statement_timeout_ms=None`이면 caller/session timeout을 유지하도록 열어뒀다.
- `load_shp_polygons(analyze=...)` docstring을 추가하고, `_analyze_target_tables()`는 테이블마다 별도 transaction으로 `ANALYZE`를 실행한다. 대상 테이블 dedup은 `_unique_target_tables()` helper로 의도를 고정했다.
- `docs/tasks.md`에 T-033(전국 full-load 재검증), T-034(SHP GDAL append 병목 튜닝), T-035(MV refresh/swap 벤치마크)를 추가했다.
- Alembic `0003_t032_performance_indexes.py`에는 대용량 운영 DB에서 일반 `CREATE INDEX`를 점검 창에 적용해야 한다는 주석을 남겼다.

**검증**: 리뷰 반영 뒤 대상 단위 테스트 41개 통과, 전체 `pytest -q` 104 passed / 7 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 세종·경남 축소 검증 1회)

**작업**: 사용자 지시에 따라 반복 횟수를 1회로 낮추고, 세종특별시·경상남도 축소 데이터만 실제 Docker DB(`kor_travel_geo_t032`)에 적재했다. 전국 full test와 반복 trial은 수행하지 않았다.

**결과**:
- `load all-sidos --no-refresh --allow-consistency-error`는 SHP 18개 layer 적재까지 완료했으나 `resolve_text_geometry_links()` 첫 UPDATE가 기본 5초 `statement_timeout`에 걸려 실패했다. 경과 2시간 1분 13초, 최대 RSS 163,672KB.
- 실패를 반영해 `resolve_text_geometry_links()`에 transaction-local 30분 timeout을 추가했다.
- 같은 DB에서 후처리만 재실행해 28.53초, 최대 RSS 77,156KB로 성공했다.
- C4/C6/C7 data-quality export는 11.25초, 최대 RSS 79,884KB로 CSV 6개를 생성했다.
- C4/C6/C7 정합성은 14.88초, 최대 RSS 80,204KB로 완료했다. `severity_max=ERROR`이며 C4 213건(`over_500m=2`), C6 77건, C7 851건이다.

**관찰**: 두 시도 축소 검증에서도 `TL_SPRD_INTRVL` 1,960,217행, `TL_SPBD_BULD` 1,324,177행 append가 전체 시간을 지배했다. GDAL `PG_USE_COPY=YES` 설정에도 `pg_stat_activity`에서는 일부 구간이 INSERT 형태로 관측되어, 후속 PR에서 GDAL COPY 강제 여부와 `TL_SPRD_INTRVL` 전용 loader를 다시 검토한다.

**검증**: 대상 단위 테스트 38개, 전체 `pytest -q` 101 passed / 7 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 성능 튜닝 범위 축소)

**작업**: PR #18 merge 이후 T-032를 시작했다. 사용자 지시에 따라 성능 튜닝 반복 기준은 기존 "10회 이상"에서 "세종특별시·경상남도 축소 데이터 1회 검증"으로 낮췄다. 전체 전국 full test와 반복 trial은 후속 안정화 단계로 미룬다.

**구현 방향**:
- C4 data-quality export는 nearest polygon 거리 계산을 `_ktg_dq_c4_distances` 임시 테이블로 한 번 만들고, sample CSV와 bucket CSV가 같은 결과를 재사용하도록 바꾼다.
- C6/C7 data-quality export는 polygon mismatch 결과를 case별 임시 violation 테이블로 한 번 만들고, sample CSV와 region summary CSV가 같은 결과를 재사용하도록 바꾼다.
- C4/C6/C7 정합성 SQL은 PostgreSQL planner가 고비용 CTE를 중복 평가하지 않도록 `MATERIALIZED` CTE를 명시한다.
- `load shp-all` 및 `load all-sidos --shp-root`는 여러 시도 SHP를 연속 적재할 때 각 시도마다 통계를 갱신하지 않고 마지막 시도 뒤 1회만 `ANALYZE`한다.

**검증 계획**: `kor_travel_geo_t032` Docker DB에서 세종특별자치시·경상남도 데이터 1회만 적재/검증한다. 현재 실행 중이며, 완료 결과와 경과 시간은 이 항목 또는 후속 항목에 이어 적는다.

## 2026-05-25 (PR #18 rebase — VWorld debug helper sync)

**작업**: 사용자 지시에 따라 T-032 성능 튜닝 전에 PR #18을 먼저 처리했다. PR #17이 main에 merge되어 `CHANGELOG.md`, `docs/journal.md`, `docs/resume.md`에서 충돌이 발생했으며, PR #17 데이터 품질 기록과 PR #18 VWorld sync 기록을 모두 보존하는 방식으로 rebase했다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과. high 기준 취약점 없음, moderate 7건은 기존 Next/PostCSS 및 Vitest/Vite 경로 잔여.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `git diff --check` → 통과.

**다음 작업**: PR #18을 푸시하고 PR 본문/코멘트를 갱신한다. PR #18 안정화 후 별도 T-032 성능 튜닝 PR을 시작한다.

## 2026-05-25 (PR #17/T-031 — 데이터 품질 export와 실제 DB 검증)

**작업**: PR #16 merge 확인 후 PR #17을 최신 `main` 위로 rebase했다. 충돌은 `docs/journal.md`, `docs/resume.md`에서만 발생했고, T-031 기록과 PR #15/VWorld 기록을 모두 보존하는 방식으로 해결했다.

**구현 상세**:
- `src/kortravelgeo/loaders/data_quality.py`를 추가했다. C2/C4/C6/C7 후속 분석용 CSV 8종(`c2_samples`, `c2_missing_key_summary`, `c4_distance_samples`, `c4_distance_buckets`, `c6/c7 samples`, `c6/c7 region_summary`)을 같은 SQL로 재현할 수 있다.
- `ktgctl validate data-quality-samples` CLI를 추가했다. `--cases C2,C4,C6,C7`, `--limit`, `--output-dir`로 산출 범위를 제어한다.
- SHP 보조 로더가 GDAL `SQLStatement` projection에 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`을 넣도록 보강했다. 기존 T-027 DB는 재적재 전이라 polygon `source_file`이 NULL이지만, 이후 재적재분부터 원천 파일 역추적이 가능하다.
- C4 sample CSV에는 출입구 좌표, 가장 가까운 polygon 대표점 좌표, `delta_lon`, `delta_lat`를 함께 넣어 500m+ 이상치의 좌표계/원천 오류 패턴을 빠르게 볼 수 있게 했다.

**실제 검증**:
- Docker DB: `kor-travel-geo-t027-db-1`, `localhost:15432`.
- `ktgctl validate data-quality-samples --cases C2,C4,C6,C7 --limit 5` → CSV 8개 생성, 2분 52.45초, 최대 RSS 79,956KB.
- `ktgctl validate data-quality-samples --cases C4 --limit 20` → C4 CSV 2개 생성, 2분 22.90초, 최대 RSS 80,008KB.
- `delta_lon`/`delta_lat` 컬럼 추가 후 `ktgctl validate data-quality-samples --cases C4 --limit 3` → 2분 18.48초, 최대 RSS 80,124KB. 상위 3건의 `delta_lon`은 각각 약 `1.9998~1.9999`도였다.
- C2 `missing_resolve_key` 581건은 모두 `rds_sig_cd` 결측으로 확인했다. 기존 DB는 PR #17 이전 적재분이라 SHP `source_file`도 NULL이다.
- C4 bucket은 `0~50=2,887,827`, `50~100=2,847`, `100~500=552`, `500+=16`이었다. 500m+ 상위 7건은 출입구 경도만 polygon보다 약 `+2.0`도 동쪽으로 튄 패턴이라, 다음 지도 overlay와 원천 row 확인 대상으로 분리한다.
- C6 상위 region은 `54002=49`, `48700=23`, `54004=15`; C7 상위 region은 `48121103=216`, `28260101=167`, `41273104=165`였다.

**검증 명령**:
- `pytest tests/unit/test_data_quality_exports.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 21 passed.
- `ruff check` 대상 파일 묶음 → 통과.

**다음 작업**: PR #17에 푸시하고 리뷰 요청한다. 안정화 후 별도 T-032 PR에서 C4/C6/C7 export 중복 스캔 제거와 full-load/postload/MV swap 속도 튜닝을 10회 이상 trial and error로 기록한다.

## 2026-05-25 (T-031 데이터 품질 후속 PR 분리)

**작업**: PR #14가 close 예정이므로, 추가 TODO를 PR #14에 계속 쌓지 않고 별도 후속 PR에서 다룰 수 있도록 T-031 문서를 추가했다.

**반영 상세**:
- `docs/t027-data-quality-followup.md`를 추가해 C2/C4/C6/C7 잔여 `ERROR`의 현재 수치, 분석 원칙, sample 산출물, 지도 확인, 원천 파일 역추적 순서를 정의했다.
- `docs/tasks.md`에 T-031을 추가하고, `docs/resume.md`의 다음 작업을 후속 PR 기준으로 바꿨다.
- `CHANGELOG.md`에 후속 분석 문서 추가를 기록했다.

**다음 작업**: T-031 PR에서는 sample 추출 SQL, 지도 확인 경로, `source_file` 추적성 보강 전략을 구현하고 실제 산출물 요약을 PR 본문에 첨부한다.

## 2026-05-25 (후속 PR — VWorld debug 동작 upstream sync)

**작업**: `maplibre-vworld-js` PR #9를 먼저 열어 `VWorldMap`의 click/error/flyTo hook과 VWorld tile error/redaction helper를 추가했다. 이어 `kor-travel-geo-ui` 후속 브랜치에서 upstream commit `11321fe`로 dependency를 동기화하고, 디버그 UI의 tile error 분류와 URL redaction을 upstream helper로 교체했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#11321fe`로 갱신했다. lockfile의 `resolved`도 SSH가 아니라 HTTPS를 유지한다.
- `kor-travel-geo-ui/lib/vworld.ts`에서 `isVWorldTileError()`와 `redactVWorldTileUrl()`를 재수출한다.
- `components/vworld/CoordinateMap.tsx`는 로컬 `isTransientTileError()`/`redactVWorldTileUrl()` 중복 구현을 제거하고 upstream helper를 사용한다. key 미설정 fallback, overlay 임계치, marker 즉시 이동, SSR dynamic wrapper는 기존 UI 계약대로 유지한다.
- VWorld helper 단위 테스트에 tile error 분류와 key redaction 검증을 추가했다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리베이스 — maplibre-vworld package 소비)

**작업**: PR #14가 main에 merge된 뒤 `codex/maplibre-vworld-ui`를 최신 `main` 위로 rebase했다. 이후 upstream `digitie/maplibre-vworld-js` main commit `a5b3c65`를 확인하고, `kor-travel-geo-ui`가 VWorld helper/CSS를 실제 `maplibre-vworld` package에서 소비하도록 갱신했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#a5b3c65`로 고정했다. CI에서 SSH key 없이 설치되어야 하므로 package-lock의 `resolved`도 `git+https`로 유지했다.
- `kor-travel-geo-ui/lib/vworld.ts`는 로컬 구현을 제거하고 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `VWorldLayerType`를 upstream package에서 재수출한다.
- 전역 CSS는 `maplibre-vworld/style.css`를 import한다. 이 package export가 MapLibre GL 기본 CSS와 package CSS를 함께 제공한다.
- upstream style source id가 `vworld-${layerType}`이고 `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 쓰므로, tile error source 판별을 `vworld` prefix 기준으로 바꿨다.
- Vitest/jsdom에서 upstream bundle이 `maplibre-gl` worker URL과 React `require()` 경로를 건드리는 문제를 테스트 setup shim으로 보정했다. 이 현상은 후속 `maplibre-vworld-js` 정합화 PR에서 upstream 테스트/번들 개선 후보로 추적한다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, README, changelog, `docs/resume.md`를 최신 package 소비 상태로 갱신했다.
- `VWorldMap` 컴포넌트 전체 대체는 이번 PR에 넣지 않고 후속 PR로 분리했다. 후속 PR은 click callback, marker 제어, tile error hook/redaction, key 미설정 fallback, SSR-safe wrapper를 `kor-travel-geo-ui`와 `maplibre-vworld-js` 사이에서 맞추는 작업이다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 20 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리뷰 보강 — VWorld MapLibre 안정화)

**작업**: PR #15 리뷰의 merge condition을 반영했다. 디버그 UI는 VWorld WMTS + MapLibre GL JS 방향을 유지하되, upstream package가 안정화되기 전까지 `maplibre-vworld` GitHub 의존성을 UI 패키지 graph에 올리지 않는 정책으로 정리했다.

**구현 상세**:
- `maplibre-vworld` 미사용 GitHub 의존성을 `kor-travel-geo-ui/package.json`과 lockfile에서 제거했다. upstream 보강은 별도 PR로 진행하고, 안정 태그 또는 SHA에서 install/build가 검증된 뒤 다시 도입한다.
- `components/vworld/LazyCoordinateMap.tsx`를 추가해 `CoordinateMap`을 `next/dynamic(..., { ssr: false })`로 지연 로딩한다. `/debug/geocode`, `/debug/reverse`는 이 wrapper만 import한다.
- `CoordinateMap.tsx`에서 VWorld tile fetch 오류를 transient로 분리했다. tile URL은 key가 드러나지 않도록 redaction한 뒤 경고 로그만 남기고, 누적 임계치 이상이거나 tile 외 오류일 때만 overlay를 표시한다.
- `lib/vworld.ts`에 레이어별 `maxZoom`을 추가했다. `Base`/`gray`/`midnight`는 z19, `Hybrid`/`Satellite`는 z18로 제한한다. attribution 표기도 `공간정보 오픈플랫폼 브이월드`로 보정했다.
- marker 위치 갱신 시 `flyTo({ animate: false, duration: 0 })`를 사용해 지도 클릭 후 불필요한 애니메이션 되튐을 줄였다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/resume.md`, changelog에 dependency 미선언 정책, dynamic import, tile error 처리, zoom 한계, CSP/key 제한 주의사항을 명시했다.
- PR 리뷰를 놓치지 않도록 `docs/resume.md`의 알려진 함정에 conversation comment와 formal review를 모두 확인하는 루틴을 추가했다.

**검증**:
- `cd kor-travel-geo-ui && npm run lint` → 통과.
- `cd kor-travel-geo-ui && npm run type-check` → 통과.
- `cd kor-travel-geo-ui && npm run test` → 7 files / 18 tests 통과. `CoordinateMap` fallback과 dynamic loading skeleton 테스트를 포함한다.
- `cd kor-travel-geo-ui && npm ci --ignore-scripts` → 통과. `maplibre-vworld` GitHub dependency 없이 cold install을 확인했다.
- `cd kor-travel-geo-ui && npm run build` → 통과. `/debug/geocode`, `/debug/reverse`가 static route로 생성되고 지도 bundle은 dynamic import 경로로 분리된다.
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여다.
- `cd kor-travel-geo-ui && npm run dev -- --hostname 127.0.0.1 --port 3001` 후 `HEAD /debug/reverse` → 200 OK. 서버 렌더 단계에서는 skeleton이 표시되고 지도 bundle은 클라이언트 chunk로 분리됨을 HTML에서 확인했다.

## 2026-05-25 (디버그 UI 지도 VWorld/MapLibre 전환)

**작업**: 사용자 지시에 따라 `kor-travel-geo-ui`의 디버그 지도 방향을 Kakao Maps SDK에서 VWorld WMTS + MapLibre GL JS로 전환했다. 실제 VWorld API key는 저장소에 기록하지 않고, `.env.local`의 `NEXT_PUBLIC_VWORLD_API_KEY`로만 주입하는 정책을 유지했다.

**구현 상세**:
- `react-kakao-maps-sdk` 의존성을 제거하고, 직접 사용하는 `maplibre-gl`을 명시 의존성으로 추가했다.
- `components/kakao/CoordinateMap.tsx`를 `components/vworld/CoordinateMap.tsx`로 교체했다. 지도 click은 기존과 동일하게 `(lon, lat)` 순서로 callback을 호출하고, marker도 EPSG:4326 좌표를 그대로 사용한다.
- `lib/vworld.ts`에 VWorld WMTS tile URL과 MapLibre raster style helper를 추가했다. `Base`/`gray`/`midnight`/`Hybrid`는 `png`, `Satellite`는 `jpeg` 타일을 사용한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 지도 로딩에 실패하면 기존처럼 같은 크기의 좌표 fallback preview를 보여 준다.

**문서화**:
- ADR-020을 추가했다. 디버그 UI 지도는 VWorld WMTS + MapLibre를 기준으로 하고, `digitie/maplibre-vworld-js`의 패키징·타입·Next.js 호환 문제가 나오면 해당 저장소도 적극 수정 대상에 포함한다고 명시했다.
- `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, `README.md`, `docs/resume.md` 등에 VWorld 지도 환경변수와 upstream 보강 원칙을 반영했다.

**검증**:
- `cd kor-travel-geo-ui && npm run lint` → 통과.
- `cd kor-travel-geo-ui && npm run type-check` → 통과.
- `cd kor-travel-geo-ui && npm run test` → 6 files / 15 tests 통과. VWorld WMTS helper 단위 테스트를 포함한다.
- `cd kor-travel-geo-ui && npm ci --ignore-scripts && npm run build` → 통과. HTTPS Git dependency lockfile 재현성을 확인했다.
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여.
- `NEXT_PUBLIC_VWORLD_API_KEY=<local only> npm run dev -- --hostname 127.0.0.1 --port 3001` 후 `HEAD /debug/reverse` → 200 OK.

## 2026-05-25 (PR #14 추가 리뷰 반영 — L1~L6, C2/C4/C6/C7 재검토)

**작업**: PR #14의 최종 리뷰 body와 thread-aware review fetch 결과를 다시 확인했다. unresolved inline thread는 없었고, 추가 반영 대상은 N1/N2와 가능하면 L1~L6, C2/C4/C6/C7 재검토였다.

**반영 상세**:
- N1: `0002_t027_shp_schema_fixups`가 기존 `tl_sprd_rw`의 `MULTILINESTRING` row 때문에 `MULTIPOLYGON` cast에서 실패하지 않도록, non-polygon row가 있으면 `tl_sprd_rw`를 먼저 `TRUNCATE`하고 타입을 변경한다. recovery/fullload 문서에도 이 destructive-but-required 동작과 이후 SHP full reset 필요성을 명시했다.
- N2/L1: MV shadow swap 인덱스 rename은 `MV_NEXT_INDEX_RENAMES` 고정 목록이 아니라 `pg_index`/`pg_class` live catalog에서 `idx_mv_next_%`를 조회해 target name을 유도한다. stale 운영 인덱스가 있어 새 next index를 drop하는 경우에는 `logging.warning`과 `warnings.warn`을 모두 남긴다.
- L2: `copy_locsum_rows()` staging 중복 제거의 tie-breaker를 `ctid`에서 temp `staging_seq BIGSERIAL`로 바꿨다. 같은 staging batch 안에서 마지막으로 copy된 row가 명시적으로 선택된다.
- L3: navi build/entrance loader가 빈 좌표뿐 아니라 `0`/`0.0` sentinel 좌표도 skip한다. EPSG:5179에서 원점 좌표는 한국 주소 데이터로 볼 수 없으므로 실제 적재 오염을 막는다.
- L5/L6: `shp-all --mode full`의 첫 시도 full, 이후 append 시퀀스를 helper와 테스트로 분리했다. GDAL PostgreSQL conninfo에는 기본 `connect_timeout=10`을 추가하고 URL query의 `connect_timeout`을 존중한다.
- C2/C4/C6/C7: C2 metric에 `missing_resolve_key`와 `missing_text`를 분리해 남은 `ERROR`의 성격을 후속 분석할 수 있게 했다. C4 metric은 `error_count=over_500m`를 명시한다. C6/C7은 경계 위 point를 false positive로 보지 않도록 `ST_Contains`에서 `ST_Covers`로 바꿨다.

**검증**:
- 대상 단위 테스트 20개 → 통과.
- `pytest -q` → 84 passed, 7 skipped.
- `ruff check .` → 통과.
- `mypy src/kortravelgeo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- 실제 T-027 Docker DB(`localhost:15432`)에서 C2/C4/C6/C7만 선택 재검증했다. 경과 3분 53.82초, 최대 RSS 80,076KB, `severity_max=ERROR`.
  - C2: 34,699건 유지. 새 metric은 `missing_text=34,118`, `missing_resolve_key=581`.
  - C4: 3,415건 유지. `over_500m=16`, `error_count=16`, `p95=3.82m`, `p99=15.50m`.
  - C6: 803건 유지. `ST_Covers` 전환 후에도 `outside_polygon=803`.
  - C7: 6,817건 유지. `ST_Covers` 전환 후에도 `outside_polygon=6,817`.

**다음 작업**: PR #14는 close 예정이므로 C2/C4/C6/C7의 원천 데이터 품질 분석, sample별 지도 확인, source_file 추적성 보강은 후속 PR에서 진행한다.

## 2026-05-25 (PR #14 리뷰 반영 — schema migration, SHP natural key, 리뷰 확인 프로토콜)

**작업**: PR #14의 정식 review body(`# PR #14 리뷰 — T-027 actual full-load execution fixes`)와 마지막 Optional conversation comment를 모두 확인하고 반영했다.

**반영 상세**:
- H1: `alembic/versions/0002_t027_shp_schema_fixups.py`를 추가했다. 기존 DB에 `tl_spbd_buld_polygon` natural key 컬럼, `tl_sprd_manage.geom`, `tl_sprd_rw.geom` `MULTIPOLYGON` 타입 변경을 적용한다.
- H2: `tl_spbd_buld_polygon.bjd_cd` generated column은 `LI_CD=''`를 `00`으로 보정하고, `rncode_full`은 빈 문자열을 NULL로 취급하도록 `SCHEMA_SQL`과 `sql/ddl/001_schema.sql`을 수정했다.
- M1: stale 운영 MV index가 남아 있어 새 `idx_mv_next_*`를 drop하는 복구 경로에서 `warnings.warn`을 남기도록 했다.
- M2: SHP full reset은 `TRUNCATE` 직전 대상 테이블별 approximate row count snapshot을 출력한다. 문서에는 full mode 중단 시 9개 SHP 테이블이 비거나 일부만 적재된 상태일 수 있음을 명시했다.
- M3/L7: 내비 loader의 `limit`은 좌표 결측 skip 이후 yield row 기준임을 docstring으로 명시하고, C4 SQL에는 `resolve_text_geometry_links()` 선행 의존성을 주석으로 남겼다.
- Optional: Docker 포트 환경변수를 저장소 prefix 규칙에 맞춰 `KTG_DB_PORT`에서 `KTG_DB_PORT`로 변경했다.
- 반복 방지: `docs/agent-guide.md`에 PR 리뷰 확인 프로토콜을 추가했다. 앞으로 PR 리뷰 반영 시 conversation comments뿐 아니라 `reviews[].body`와 `review_threads[]`를 반드시 확인한다.

**검증**:
- `pytest tests/unit/test_alembic_migrations.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_shp_loader_gdal.py tests/unit/test_postload_mv.py tests/unit/test_navi_loader.py tests/unit/test_consistency_sql.py -q` → 17 passed.
- `ruff check .` → 통과.
- `mypy src/kortravelgeo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- `PATH="$PWD/.venv/bin:$PATH" DATA_DIR=/home/digitie/kor-travel-geo-data KTG_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` → 통과. 출력 DSN은 `localhost:15432`.
- `pytest -q` → 80 passed, 7 skipped.
- 임시 DB `kor_travel_geo_pr14_review`에서 `alembic upgrade head` → 0001, 0002 적용 성공. `LI_CD=''` 샘플 insert 시 generated `bjd_cd=1111010100`, `rncode_full=111103100012` 확인.
- 실제 T-027 DB 영향 조회: `empty_li=0`, `empty_rn=0`, `empty_rds_sig=0`, `bjd_8=0`, `bjd_10=10,687,732`.

## 2026-05-25 (PR #14/T-027 — 실제 전국 SHP 재적재와 정합성 재검증)

**작업**: `data/juso/도로명주소 전자지도` 실제 전국 SHP 17개 시도 × 9개 레이어를 새 natural-key 스키마로 Docker PostGIS에 재적재하고, C1~C10 정합성 검증을 실제 DB에서 재실행했다.

**실행 로그**:
- 상세 로그: `artifacts/fullload/20260524_173115/execution-log.md` (git ignore 산출물)
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Python 3.12.3, GDAL 3.8.4
- DB: `kor-travel-geo-t027-db-1`, `localhost:15432`, `kor_travel_geo`
- SHP 재적재 경과: 3시간 10분 4초, exit status 0, 최대 RSS 187,100KB
- 종료 직후 DB 크기: 24GB
- 디스크 여유: ext4 약 796GB, C: 약 682GB, F: 약 264GB

**확정 row count**:
- `tl_scco_ctprvn`: 17
- `tl_scco_sig`: 255
- `tl_scco_emd`: 5,067
- `tl_scco_li`: 15,161
- `tl_kodis_bas`: 34,516
- `tl_sprd_manage`: 875,221
- `tl_sprd_rw`: 1,482,679
- `tl_sprd_intrvl`: 16,993,167
- `tl_spbd_buld_polygon`: 10,687,732

**발견한 문제**:
- `TL_SPBD_BULD` natural key(`rncode_full`, `bjd_cd`, 건물구분, 본번, 부번)는 중복 polygon을 많이 가진다. 같은 natural key에 polygon이 여러 개인 경우 C4/C5가 모든 후보와 다대다 거리값을 만들며 180km급 이상치를 대량 보고했다.
- `rds_sig_cd`/`rncode_full`이 NULL인 SHP 건물 polygon이 581건 있었다. 나머지 natural-key 컬럼과 geometry는 전 건 채워졌다.
- `source_file` 컬럼은 현재 GDAL append 경로에서 전 건 NULL이다. 적재 추적성 보강 후보로 남긴다.
- 대부분 시도 `TL_SPRD_RW.shp`, 일부 `TL_SPBD_BULD.shp`/행정구역 polygon에서 GDAL ring winding order 자동 보정 경고가 반복됐다. 적재는 실패 없이 완료됐다.
- 실제 smoke test에서 `geocode` SQL의 `:si IS NULL` 선택 필터가 psycopg `AmbiguousParameter`를 일으켰다. PostgreSQL은 `IS NULL`에 먼저 등장한 바인딩 파라미터의 타입을 추론하지 못할 수 있다.

**보강 상세**:
- C4는 같은 natural key SHP polygon 후보 중 `e.geom <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 `JOIN LATERAL ... LIMIT 1`로 수정했다.
- C5는 같은 natural key SHP polygon 후보 중 `n.centroid_5179 <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 수정했다.
- 단위 테스트는 C4/C5가 LATERAL nearest 후보를 사용함을 확인하도록 보강했다.
- `geocode`, `zipcode`, `pobox` raw SQL의 optional filter는 `CAST(:param AS text/integer/boolean)`로 명시해 psycopg 타입 추론 실패를 막았다.

**정합성 결과**:
- 1차 재검증: 4분 59.41초, `severity_max=ERROR`
  - C4: 257,783건, `over_500m=11,649`
  - C5: 3,277,327건
- C4/C5 nearest 보강 후 2차 재검증: 6분 27.54초, `severity_max=ERROR`
  - C1 WARN: 32,531건
  - C2 ERROR: 34,699건
  - C3 WARN: 3,510,265건
  - C4 ERROR: 3,415건, `over_500m=16`, `p95=3.82m`, `p99=15.50m`
  - C5 WARN: 202건
  - C6 ERROR: 803건
  - C7 ERROR: 6,817건
  - C8 WARN: 24,471건
  - C9 OK: 0건
  - C10 OK: 0건

**검증**:
- `ruff check src/kortravelgeo/loaders/consistency.py tests/unit/test_consistency_sql.py` 통과.
- `pytest tests/unit/test_consistency_sql.py -q`는 pytest capture 임시파일 `FileNotFoundError`로 테스트 실행 전 실패.
- `pytest -s tests/unit/test_consistency_sql.py -q` → 2 passed.
- SHP 9개 테이블 `ANALYZE` → 4.14초, 성공.
- `ruff check src/kortravelgeo/infra/geocode_repo.py src/kortravelgeo/infra/zip_repo.py src/kortravelgeo/infra/pobox_repo.py tests/unit/test_infra_repo_sql.py` 통과.
- `pytest -s tests/unit/test_infra_repo_sql.py tests/unit/test_consistency_sql.py -q` → 12 passed.
- smoke test: `서울특별시 종로구 필운대로 93` geocode OK, reverse OK(10건), search 3건, zipcode OK(3건).

**다음 작업**: C4/C5 nearest 보강을 커밋·푸시하고 PR #14에 실제 전수 적재/정합성 결과를 코멘트한다. 이어서 MV/클라이언트 smoke와 전체 테스트를 가능한 범위까지 수행하고, 남은 C2/C4/C6/C7 원천 데이터 품질 항목은 후속 분석 후보로 분리한다.

## 2026-05-24 (PR #14/T-027 — 실제 SHP 적재 중 GDAL/PostGIS 스키마 보강)

**작업**: 실제 `data/juso/도로명주소 전자지도`를 Docker PostGIS에 적재하는 과정에서 SHP 로더의 GDAL 옵션, geometry 타입, full-load overwrite 전략 문제를 확인하고 보강했다.

**발견한 문제**:
- GDAL 3.8 Python binding은 `VectorTranslateOptions(openOptions=...)`를 받지 않아 SHP 적재가 `TypeError`로 중단되었다.
- `openOptions` 제거 후에는 `accessMode="overwrite"`가 운영 테이블을 원천 DBF 스키마로 재생성하면서 `tl_scco_ctprvn.geom`이 `Polygon`으로 바뀌었고, 실제 `MultiPolygon` 삽입에서 실패했다.
- `shp-all --mode full`은 17개 시도 디렉터리를 순회하는데, 각 시도마다 overwrite/full을 그대로 적용하면 앞 시도 데이터가 뒤 시도 적재 때 사라질 수 있다.
- 실제 2026년 전자지도 17개 시도 파일을 확인한 결과 `TL_SPRD_RW.shp`는 모두 `Polygon` 레이어다. 기존 `tl_sprd_rw.geom geometry(MultiLineString, 5179)` 정의와 맞지 않았다.
- 실패 후 복구를 위해 `init-db`를 다시 실행하자, 이미 대량 텍스트 데이터가 들어간 상태에서는 MV 생성이 5초 statement timeout에 걸렸고 같은 트랜잭션의 앞선 DDL까지 롤백될 수 있음을 확인했다.

**보강 상세**:
- SHP 로더는 CP949를 `gdal.config_options({"SHAPE_ENCODING": "CP949"})`로 지정한다.
- full 모드는 대상 9개 테이블을 명시적으로 `TRUNCATE`한 뒤 GDAL은 항상 기존 PostgreSQL 테이블에 `append`한다. 원천 DBF 전체 컬럼으로 운영 테이블을 재생성하지 않는다.
- `SQLStatement`는 JOIN 키와 필요한 속성 컬럼만 alias한다. OGR SQL 결과가 geometry를 유지하므로 `GEOMETRY AS geom` 같은 가짜 문자열 필드를 만들지 않는다.
- `shp-all --mode full`과 `load all-sidos --shp-root`는 첫 시도만 full, 이후 시도는 append로 바꿔 전국 적재가 누적되도록 했다.
- `tl_sprd_rw.geom`은 실제 SHP 헤더에 맞춰 `MULTIPOLYGON 5179`로 조정하고 문서도 도로면 polygon 기준으로 갱신했다.
- `init-db`는 schema/index/MV statement를 별도 트랜잭션으로 실행해 MV 경고가 schema DDL을 롤백하지 않게 했다. 경고가 있으면 개수를 출력한다.
- `refresh mv --swap`은 복구 중 기존 `mv_geocode_target`이 없어도 `mv_geocode_target_next`를 바로 운영 이름으로 승격한다. swap 후 `ANALYZE mv_geocode_target`도 수행한다.
- `scripts/fullload_test.sh`는 기본 `KTG_PG_STATEMENT_TIMEOUT_MS`를 30분으로 높인다. 대량 링크 해소와 shadow MV 빌드가 운영 기본값 5초에 막히지 않도록 하기 위함이다.
- 실제 MV 빌드 후 `pt_source='centroid'`가 0건인 것을 확인했다. 원인은 내비게이션용DB의 `bd_mgt_sn`이 25자리이고 정본 `tl_juso_text.bd_mgt_sn`은 26자리라 직접 조인이 불가능한 점이었다. 또한 내비 `bjd_cd`는 리 코드가 `00`인 경우가 많아 10자리 법정동 완전 일치도 부적합했다. MV fallback을 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 대표 centroid 조인으로 변경했다.
- 두 번째 MV swap에서 `idx_mv_next_geocode_target_next_pk`가 이미 존재한다는 충돌을 확인했다. 첫 swap 때 shadow MV 인덱스명이 운영 MV에 그대로 남았기 때문이다. swap 전후에 `idx_mv_next_*` 이름을 운영명 `idx_mv_*`로 정규화하도록 보강했다. 이어 실제 재시도에서 old MV의 운영명 인덱스가 아직 있는 상태로 next 인덱스를 rename하려 하면 next 인덱스가 drop되는 것을 확인해, old MV를 먼저 drop한 뒤 next 인덱스를 rename하도록 순서를 조정했다.
- 실제 C1~C10 정합성 검증에서 C1/C2가 전량 불일치했다. `TL_SPBD_BULD.BD_MGT_SN`도 25자리이고 정본은 26자리라 건물 polygon도 직접 `bd_mgt_sn` 조인이 불가능했다. `tl_spbd_buld_polygon`에 `RDS_SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `SIG_CD`, `EMD_CD`, `LI_CD`를 함께 적재하고 C1/C2/C4/C5를 natural key 기준으로 바꿨다. C8은 `TL_SPRD_RW`에 `rds_man_no`가 없어 전량 WARN이 나므로, `TL_SPRD_MANAGE` LineString geometry를 적재해 도로 인접성 검증에 사용하도록 바꿨다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 6 passed.
- `.venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py src/kortravelgeo/cli/main.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py` → 통과.
- 실패로 오염된 SHP 보조 테이블 9개만 drop 후 `KTG_PG_DSN=...15432 .venv/bin/ktgctl init-db` 재실행. MV 생성은 timeout 경고가 났지만 SHP 테이블 스키마는 `MULTIPOLYGON 5179`로 복구됨을 확인했다.
- `세종특별자치시` 실제 SHP 9개 레이어 적재 성공: 59.09초, 최대 RSS 약 128MiB, `tl_spbd_buld_polygon` 55,819행, `tl_sprd_intrvl` 100,009행 등 9개 테이블 row count 확인.
- 전국 SHP 153개 레이어 적재 성공: 3시간 1분 34초, 최대 RSS 약 181MiB. 정확한 row count는 `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행 등으로 확인했다.

**다음 작업**: 변경분을 PR #14에 푸시하고, 같은 Docker DB에서 전국 `shp-all --mode full`을 재실행한다. 이후 pobox/bulk optional 단계, 링크 해소, MV swap, C1~C10 정합성, smoke test를 순서대로 계속 진행한다.

## 2026-05-24 (PR #14/T-027 — 실제 데이터로드 실행 중 포트 충돌 방지)

**작업**: PR #13이 main에 머지된 뒤 `codex/t027-fullload-execution` 브랜치에서 실제 데이터로드를 시작했다. WSL ext4 클론(`~/dev/kor-travel-geo`)에서 Python/GDAL 환경을 만들고, `F:\dev\kor-travel-geo\data` 원본을 `~/kor-travel-geo-data` 작업 사본으로 복사했다.

**실행 로그**:
- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 기록한다.
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Docker Compose v5.1.4, Python 3.12.3, GDAL 3.8.4.
- `--copy-data` 시작 `2026-05-24T17:31:15+09:00`, 종료 `2026-05-24T18:35:47+09:00`, 경과 약 1시간 4분 32초.
- 복사 결과: `~/kor-travel-geo-data/juso` 약 25GB, 파일 683개. `epost`는 현재 원본 파일이 없어 빈 디렉터리다.

**발견한 문제**:
- 로컬 5432 포트가 기존 `airflow-postgres-1` 컨테이너에서 이미 사용 중이었다.
- T-027 기본 compose/스크립트가 `localhost:5432`를 그대로 사용하면 기존 DB에 DDL/적재를 실행할 위험이 있다.

**보강 상세**:
- 당시 인프라 설정 파일의 외부 포트를 `${KTG_DB_PORT:-5432}:5432`로 파라미터화했다.
- `scripts/fullload_test.sh`는 `KTG_PG_DSN`이 없을 때 `KTG_DB_PORT`를 반영한 DSN을 만든다.
- `docs/t027-fullload-plan.md`, `docs/dev-environment-recovery.md`, `CLAUDE.md`에 `KTG_DB_PORT=15432` 사용 예와 포트 충돌 주의사항을 추가했다.

**검증**:
- `bash -n scripts/fullload_test.sh` 통과.
- `DATA_DIR=/home/digitie/kor-travel-geo-data KTG_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` 통과. 출력 DSN이 `localhost:15432`로 바뀌는 것을 확인했다.
- `git diff --check` 통과.

**다음 작업**: PR 생성 후 `KTG_DB_PORT=15432`로 Docker PostGIS를 기동하고 실제 적재를 계속 진행한다. 이후 발견되는 문제는 같은 PR에 누적한다.

## 2026-05-24 (PR #13/T-027 — Windows 재설치·Codex 세션 복구 문서화)

**작업**: Windows 재설치 후 `git pull`로 PR #13 작업을 문제없이 이어갈 수 있도록 복구 절차를 문서화했다. 실제 Docker 전체 적재와 `PLAN_ONLY=1` 실행은 하지 않았다.

**보강 상세**:
- `docs/windows-reinstall-recovery.md`를 추가했다. Git branch/PR을 영속 상태의 기준으로 두고, `data/`·`.env`·API 키·WSL distro·Docker volume의 백업 여부를 구분했다.
- 재설치 후 WSL/GDAL/Python 환경 복구, PR #13 브랜치 checkout, `docs/t027-fullload-plan.md` 확인, `PLAN_ONLY=1 bash scripts/fullload_test.sh` preflight 순서를 명시했다.
- Codex 레벨 복구는 repo에 넣을 내용과 로컬 세션 편의 기능을 분리했다. 문서에는 일반적인 `codex resume`, `codex fork`, `codex doctor`, `codex cloud` 확인 명령과 `CODEX_HOME`/`.codex` 백업 주의사항만 남겼다.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/dev-environment.md`, `docs/dev-environment-recovery.md`, `docs/resume.md`에서 새 복구 문서를 참조하도록 연결하고, 실제 적재는 사용자 명시 전 실행하지 않는 금지선을 맞췄다.

**다음 작업**: PR #13 리뷰 후에도 실제 전체 적재는 바로 실행하지 않는다. 먼저 문서와 스크립트 syntax 확인을 거친 뒤, 사용자가 허용하면 `PLAN_ONLY=1` preflight 결과를 PR에 공유한다.

## 2026-05-24 (PR #13/T-027 — Docker full-load 계획 보강)

**작업**: 사용자 지시에 따라 실제 Docker 전체 적재 실행은 중단하고, `F:\dev\kor-travel-geo\data\juso` 전체를 대상으로 한 계획/문서/스크립트 preflight 보강만 진행했다. 로컬 파일 시스템은 목록과 용량만 확인했고 DB 적재·Docker 실행은 하지 않았다.

**확인한 데이터 인벤토리**:
- `data/juso` 전체는 약 28GB다.
- 현재 full-load에 바로 쓸 수 있는 자료는 `202603_도로명주소 한글_전체분`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분`, `도로명주소 전자지도`다.
- `daily/*.zip`, `jibun_rnaddrkor_*`, `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`는 현재 로더의 직접 적재 대상이 아니므로 후속 태스크로 분리했다.

**보강 상세**:
- `docs/t027-fullload-plan.md`를 실행 전 리뷰 가능한 계획서로 재작성했다. 실행 금지선, Docker project/volume 안전장치, 기준월 분리, phase별 중단·재개, 산출물 경로, 미지원 자료 후속 태스크를 명시했다.
- `scripts/fullload_test.sh`는 실행 산출물로 남기되 `PLAN_ONLY=1` preflight를 추가했다. 단일 `YYYYMM` 대신 `JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`을 분리하고, CLI 호출은 `kor-travel-geo` console script로 맞췄다.
- 초안 스크립트의 DDL inline SQL 실행을 `alembic upgrade head`로 바꾸고, 별도 적재 명령 뒤 누락될 수 있는 `resolve_text_geometry_links()`를 명시적으로 수행하도록 정리했다. MV 갱신은 full-load에 맞게 `refresh mv --swap`을 기본으로 둔다.
- smoke test는 실제 DTO 구조(`GeocodeResponse.result.point`, `ReverseResponse.result`, `SearchResponse.result`, `ZipcodeResponse.result`)에 맞게 보정했다.

**검증**:
- `bash -n scripts/fullload_test.sh` → 통과. 실제 DB/Docker 적재 실행은 하지 않았다.

**다음 작업**: PR #13 리뷰 후 `PLAN_ONLY=1 bash scripts/fullload_test.sh`만 먼저 실행한다. 전체 적재는 Docker 볼륨/로그 경로/중단 기준을 확인한 뒤 별도 지시가 있을 때 진행한다.

## 2026-05-24 (PR #12 리뷰 보강 — 보안·CI·에러 처리)

**작업**: PR #12 top-level 리뷰 코멘트를 확인했다. inline review thread는 없었고, GitHub 기준 mergeable 상태라 Git 충돌은 없었다. 다만 backend CI가 `scripts.export_openapi` import 실패로 깨졌고, 리뷰의 C/H/M 항목과 추가 코멘트의 프록시 스트리밍 항목을 모두 코드로 반영했다.

**구현 상세**:
- C1/C2: `/v1/admin/upload/sido-zip`에서 `sido`와 `filename`을 path token으로 정규화하고, resolved path가 `loader_data_dir/uploads` 밖으로 나가면 `InvalidInputError(E0100)`로 거절한다. `api_max_upload_bytes`(기본 2GiB)를 추가해 초과 업로드는 partial file 삭제 후 실패시킨다.
- H1/L1: Next.js 프록시는 `new URL()` 정규화 이후 `/v1/` 하위 경로만 허용하고, 전달 헤더를 `accept`/`content-type`/`user-agent`로 제한한다.
- 추가 코멘트: Next.js 프록시는 더 이상 `request.arrayBuffer()`로 업로드 본문 전체를 메모리에 올리지 않는다. GET/HEAD 외 요청은 `request.body` `ReadableStream`을 그대로 넘기고 Node.js fetch 요건에 맞춰 `duplex: "half"`를 설정한다.
- H2: `ApiError`를 추가해 HTTP status를 보존하고, React Query retry가 4xx를 재시도하지 않게 했다.
- H3: `/v1/admin/explain`은 실행 전 `set_config('statement_timeout', ..., true)`를 호출한다. 기본 timeout은 `api_explain_timeout_ms=3000`.
- M1~M3/L2/L3: `LoadConsole`, `ReverseDebugger`, `ConsistencyPanel` 에러 처리를 보강하고 빈 jobs 배열 finished 전이를 막았다.
- M4: Prometheus gauge 이름을 `kor_travel_geo_cache_hits_total`에서 `kor_travel_geo_cache_hits`로 변경했다.
- M5: `ExplainDebugger`가 `explainFormSchema`를 사용해 SELECT/WITH와 세미콜론 금지를 클라이언트에서도 검증한다.
- CI: `scripts/__init__.py`를 추가하고 pytest `pythonpath`에 repository root를 명시해 GitHub Actions의 pytest 수집 환경에서도 `scripts.export_openapi` import가 안정적으로 동작하게 했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 70 passed, 1 skipped
- 임시 DB `kor_travel_geo_codex_pr12_review`에서 `KTG_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed
- `cd kor-travel-geo-ui && npm run lint && npm run type-check && npm run test && npm run build` → 통과, Vitest 12 passed
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과, moderate advisory만 잔여

**다음 작업**: PR #12 CI 재확인과 리뷰어 코멘트 답변.

## 2026-05-23 (PR #12 — T-021~T-026 프론트엔드·관측·CI 구현)

**작업**: PR #11을 main에 머지한 뒤, PR #11 후속 의견을 PR #12로 이관했다. PR #12 범위는 T-018~T-020이 main에 이미 포함된 상태에서 T-021~T-026을 실제 코드와 테스트로 마무리하는 것이다.

**구현 상세**:
- T-021: `kor-travel-geo-ui` 패키지를 추가했다. Next.js 16(App Router), React 18, Tailwind, TanStack Query, `react-kakao-maps-sdk`, OpenAPI 타입 생성 스크립트(`npm run gen:types`)를 포함한다.
- T-022: `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 페이지를 구현했다. 모든 요청은 `/api/proxy/[...path]` Route Handler를 통해 백엔드 `/v1/*`로 전달한다. Kakao JS key가 없으면 지도는 좌표 프리뷰로 fallback한다.
- T-023: `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs` 페이지를 구현했다. full-load batch payload 등록, raw ZIP 업로드, MV refresh enqueue, 테이블 통계, 캐시 메트릭, `load_jobs.log_tail` 조회를 확인할 수 있다.
- T-024: 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가했다. backend lint/type/import/test와 frontend type generation drift/lint/type/test/build를 분리된 job으로 검증한다.
- T-025: `infra/metrics.py`와 `/metrics` endpoint를 추가했다. 외부 API 호출 결과, cache entries/hits/expired, load job kind/state 분포를 Prometheus 포맷으로 노출한다.
- T-026: `/admin/consistency` 페이지를 추가했다. C1~C10 report 목록, 상세 case grid, 원본 JSON, 재검증 enqueue를 제공한다.
- FastAPI admin 라우터와 `AsyncAddressClient`에 `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv` 표면을 연결했다.

**결정**:
- ADR-019를 추가했다. 신규 프론트엔드는 Next.js 14가 아니라 Next.js 16을 보안 하한선으로 둔다. `npm audit --omit=dev --audit-level=high`가 통과해야 한다.
- `/v1/admin/upload/sido-zip`은 `python-multipart` 의존을 피하기 위해 multipart가 아닌 raw request body stream + query `filename` 형태로 구현했다. Next.js 프록시는 body를 `arrayBuffer()`로 읽어 그대로 전달한다.
- `ruff format --check`는 기존 파일 포맷 churn이 커서 PR #12 CI 범위에서 제외했다. 이번 PR은 `ruff check`, `mypy`, `lint-imports`, `pytest`를 품질 게이트로 삼는다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`
- `KTG_TEST_PG_DSN=... .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` — 실제 `data/juso` 샘플 COPY와 MV 생성 검증
- `cd kor-travel-geo-ui && npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build`
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high`

**다음 작업**: PR #12 리뷰 대기. 후속 후보는 `/admin/load` 업로드 진행률(XHR progress), `/admin/logs` streaming tail, `/debug/reverse` 지도 클릭 즉시 조회 UX다.

## 2026-05-23 (PR #11 follow-up — batch payload fail-fast 검증)

**작업**: PR #11 후속 확인 결과 GitHub review thread/comment는 없었지만, 원격 브랜치에 `AsyncAddressClient.submit_load("full_load_batch", ...)`를 `insert_load_batch`로 라우팅하는 보강 커밋이 추가되어 있었다. 해당 방향은 REST와 라이브러리 표면을 일치시키므로 타당하다고 판단했고, 그 위에 잘못된 batch payload가 `load_jobs`에 root + 빈 child를 먼저 남기는 문제를 추가로 막았다.

**구현 상세**:
- `infra.batch.batch_children()`에서 enqueue 전 payload 검증을 수행한다. 기본 `payloads` 경로는 ADR-017 source child 5종(`juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`) 모두에 `path` 또는 `source_path`가 있어야 한다.
- 명시 `children`/`child_jobs` 배열은 더 이상 잘못된 entry를 조용히 버리지 않는다. entry object, non-empty `kind`, object `payload`를 요구하고, 경로 기반 로더(`bulk_load` 포함)는 `path`/`source_path`가 없으면 `InvalidInputError(E0100)`를 던진다.
- `AsyncAddressClient.submit_load("full_load_batch", ...)`는 검증 실패 시 `AdminRepository.insert_load_batch`와 `insert_load_job` 어느 쪽도 호출하지 않으므로, 불완전한 batch root가 DB에 영속되지 않는다.
- `docs/backend-package.md`에 `full_load_batch` payload 예시와 검증 정책을 자세히 추가했다. REST와 라이브러리 표면이 같은 helper를 공유한다는 점을 명시했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_infra_batch.py tests/unit/test_client_submit_load_batch.py -q` → 14 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 65 passed, 1 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- 임시 DB `kor_travel_geo_codex_pr11_followup`에서 `KTG_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` 실행 → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed.

**다음 작업**: PR #11에 후속 의견과 검증 결과를 남긴 뒤, 리뷰어가 원하면 payload schema를 OpenAPI DTO 수준에서 더 좁히는 작업을 별도 PR로 분리한다.

## 2026-05-23 (PR #11 리뷰 fixup — 라이브러리 batch DAG 비대칭 해소)

**작업**: PR #11 리뷰에서 발견된 라이브러리/REST 비대칭 이슈를 해결했다. `AsyncAddressClient.submit_load("full_load_batch", ...)`가 `AdminRepository.insert_load_job`을 직접 호출하던 경로를 `insert_load_batch`로 라우팅하여, 라이브러리 사용자도 REST `/v1/admin/loads`와 동일하게 root + 5종 child + DAG가 즉시 적재되도록 한다.

**구현 상세**:
- `src/kortravelgeo/infra/batch.py` 신규 모듈에 `BATCH_SOURCE_KINDS`와 `batch_children()`을 이동했다. `api/_jobs.py`의 동명 private 헬퍼는 제거하고 새 모듈을 import한다.
- `AsyncAddressClient.submit_load`는 `kind == "full_load_batch"`일 때 `batch_children(payload)`로 child 구성을 결정해 `AdminRepository.insert_load_batch`를 호출한다. 비-batch kind는 종전대로 `insert_load_job`을 사용한다.
- `infra/batch.py`는 `core/dto` 의존 없는 순수 모듈이라 client / api / loaders 어느 레이어에서도 import 가능. import-linter "Layered architecture" 컨트랙트 유지.

**검증**:
- `tests/unit/test_infra_batch.py` 신규 — default kind 순서, `payloads` 매핑 키, 명시 `children` 우선, 잘못된 entry drop을 검증.
- `tests/unit/test_client_submit_load_batch.py` 신규 — `AsyncMock`으로 `insert_load_batch` / `insert_load_job` 호출 분기를 검증.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest tests/unit/ -q` → 51 passed.
- `python -m ruff check`, `mypy --strict src/kortravelgeo/api/_jobs.py src/kortravelgeo/infra/batch.py src/kortravelgeo/client.py`, `lint-imports` 모두 통과.
- `python scripts/export_openapi.py --check` → drift 없음 (DTO 변경 없음).

**다음 작업**: T-021 프론트엔드 패키지 `kor-travel-geo-ui` 부트스트랩.

## 2026-05-23 (codex, T-018~T-020 구현 + 신규 PR 준비)

**작업**: PR #10 리뷰 fixup 위에서 T-018~T-020을 추가 구현하고, 사용자 요청대로 P1/P2 리뷰 반영 사항과 T-005~T-020 완료 범위를 하나의 신규 PR로 등록할 준비를 진행했다.

**구현 상세**:
- T-018: CLI 운영 명령을 확장했다. `ktgctl load all-sidos`는 juso/locsum/navi 필수 경로와 선택 SHP/epost 보조 경로를 받아 직접 적재 → 링크 해소 → C1~C10 정합성 검증 → optional MV refresh까지 묶는다. `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`도 추가했다.
- T-019: `infra/external_api.py`를 추가했다. `AsyncAddressClient.geocode(..., fallback="api")`는 로컬 DB 결과가 `NOT_FOUND`일 때만 외부 폴백을 호출한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 API + 좌표 API다. 외부 응답은 기존 `GeocodeResponse`로 변환하며 공급자 출처는 `x_extension.source`에만 둔다.
- T-020: `scripts/export_openapi.py`를 추가해 `create_app().openapi()`를 `openapi.json`으로 내보낸다. `--check` 모드는 committed schema와 생성 결과가 다르면 실패한다. `.github/workflows/openapi.yml`은 PR마다 `.[api]` extra 설치 후 drift 검사를 실행한다.

**문서**:
- `docs/tasks.md`에서 T-018~T-020을 완료로 이동했다.
- `docs/resume.md`의 다음 작업을 T-021 프론트엔드 부트스트랩으로 갱신했다.
- `docs/backend-package.md`에 외부 API fallback 흐름과 OpenAPI export/CI drift 절차를 명시했다.
- `docs/external-apis.md`에 구현 위치, 호출 순서, 응답 매핑 정책을 보강했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 51 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN` 미설정 시 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_t020_verify' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kor_travel_geo_codex_t020_verify` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → 통과

## 2026-05-23 (codex, PR #10 리뷰 코멘트 반영)

**작업**: PR #10 상위 리뷰 코멘트의 P1/P2 항목을 반영했다. P1은 ADR-017 batch DAG, C1~C10 정합성 검증, PNU NULL guard이고, P2는 reverse `both`, 텍스트 인코딩 fallback, `load_jobs` 진행률/log_tail, `x_extension` ADR 문서화를 중심으로 처리했다.

**주요 변경**:
- `load_jobs`에 `load_batch_id`, `parent_job_id`를 추가하고 `full_load_batch` root job 아래 source load child 5종 → `consistency_check` → `mv_refresh(strategy='swap')` 순서로 이어지는 batch DAG를 구현했다.
- `JobQueue` handler 시그니처를 `(payload, cancel_event, progress_cb)`로 확장했다. `progress_cb`는 `progress`, `current_stage`, `heartbeat_at`, `log_tail`을 DB에 갱신한다.
- FastAPI lifespan에서 기본 handler를 등록한다. `juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`, `consistency_check`, `mv_refresh`가 큐에서 실제 실행된다.
- `loaders/consistency.py`를 C1~C10 전체 케이스로 확장했다. 각 케이스는 `count`, `ratio`, `threshold`, `metric`, `sample`을 채운다. C4/C6/C7/C9는 `ERROR` 판정 근거가 명시되어 batch swap gate로 쓸 수 있다.
- `tl_juso_text.pnu` generated column에 `mntn_yn IS NULL` 가드를 추가했다. 실제 `rnaddrkor_seoul.txt` 524,678건은 `bd_mgt_sn` 길이가 모두 26자리였으므로, 체크 제약은 `BETWEEN 25 AND 26`으로 좁혔다.
- reverse `type="both"`가 도로명과 지번 결과를 모두 반환하도록 보정했다.
- 텍스트 인코딩 감지는 BOM → CP949 검증 → UTF-8 검증 순서로 바꿨다.
- ADR-017(batch DAG)과 ADR-018(`x_extension` 스키마 격리)을 `docs/decisions.md`에 추가했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 47 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_pr10_fix' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kor_travel_geo_codex_pr10_fix` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept

**다음**: PR #10에 반영 요약과 검증 결과를 코멘트로 남긴다.

## 2026-05-23 (codex, T-005~T-017 일괄 구현 + 실제 파일/DB 검증)

**작업**: PR #7이 닫힌 뒤 최신 `origin/main`(`fa276dd`)에서 새 브랜치 `codex/t017-text-primary-load`를 만들고, ADR-012/ADR-016 기준으로 T-005부터 T-017까지 백엔드 1차 구현을 진행했다. 사용자의 추가 지시대로 `data/juso` 실제 파일을 반드시 열어 검증했고, 로컬 PostGIS에 별도 테스트 DB를 만들어 실제 샘플 COPY 적재와 MV 생성까지 확인했다.

**변경 파일(주요)**:
- 신규: `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_text_primary_postgis_schema.py`
- 신규: `src/kortravelgeo/infra/engine.py`, `infra/sql.py`, `infra/pnu.py`, `infra/geocode_repo.py`, `infra/reverse_repo.py`, `infra/search_repo.py`, `infra/zip_repo.py`, `infra/pobox_repo.py`, `infra/admin_repo.py`
- 신규: `src/kortravelgeo/core/protocols.py`, `core/normalize.py`, `core/geocoder.py`, `core/reverse_geocoder.py`, `core/searcher.py`, `core/zipcoder.py`, `core/poboxer.py`, `core/responses.py`
- 갱신: `src/kortravelgeo/client.py`, `src/kortravelgeo/__init__.py`, `src/kortravelgeo/dto/admin.py`, `src/kortravelgeo/cli/main.py`
- 신규: `src/kortravelgeo/api/app.py`, `api/_jobs.py`, `api/deps.py`, `api/responses.py`, `api/routers/*`
- 신규: `src/kortravelgeo/loaders/text/juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`, `loaders/shp/polygons_loader.py`, `shp/delta_loader.py`, `loaders/postload.py`, `loaders/consistency.py`, `loaders/pobox_loader.py`, `loaders/bulk_loader.py`, `loaders/manifest.py`
- 신규 테스트: `tests/unit/test_infra_engine_pnu_sql.py`, `test_core_geocoder.py`, `test_infra_repo_sql.py`, `test_api_app_contract.py`, `tests/integration/test_real_juso_text_loaders.py`, `test_optional_real_postgres_load.py`
- 갱신 문서: `docs/tasks.md`, `docs/resume.md`, `docs/data-model.md`, `docs/backend-package.md`, `CHANGELOG.md`

**구현 상세**:
- T-005: `make_async_engine()`은 `Settings.pg_dsn` 보정을 신뢰하고, statement timeout과 `search_path=public,x_extension`를 연결 옵션에 넣는다. PostGIS/pg_trgm/unaccent는 `x_extension` 스키마에 설치한다.
- T-006/T-007: DDL은 텍스트 4 + SHP polygon/폴리라인 9 + 우편번호 보조 2 + 메타 5 = 20개 테이블을 만든다. `mv_geocode_target`은 `pt_5179`, `pt_4326`, `pt_source`를 노출하고 `pt_5179 IS NOT NULL` partial GiST index를 둔다. `tl_juso_text.pnu`는 `COALESCE(lnbr_mnnm, 0)` 없이 필수 필드 결측 시 `NULL`을 반환한다.
- T-008~T-010: 주소 정규화(`parse_address`)와 geocode core/repo를 구현했다. 도로명 fuzzy는 트랜잭션 안에서만 `SET LOCAL pg_trgm.similarity_threshold`를 사용한다.
- T-011/T-016: `AsyncAddressClient`가 실제 raw SQL repo를 연결해 geocode/reverse/search/zipcode/pobox를 호출한다. load job과 consistency report 조회/등록/취소 표면도 추가했다.
- T-012/T-015: FastAPI 앱과 `/v1/address/*`, `/v1/admin/loads`, `/v1/admin/consistency/*` 라우터를 추가했다. `JobQueue`는 DB `load_jobs`를 기준으로 상태를 영속화하고 startup에서 잔존 `running`을 `failed` 처리한다. 실행 직전 `pg_try_advisory_xact_lock` + `FOR UPDATE SKIP LOCKED`로 다중 워커 중복 실행을 막는다.
- T-013a~c: 텍스트 로더는 실제 파일 기반 인덱스를 박아 `psycopg.copy()`로 적재한다. 위치정보요약DB 실제 ZIP은 `bd_mgt_sn`을 직접 제공하지 않으므로 natural key를 보관하고 후처리에서 `tl_juso_text`와 조인해 해소한다. 일부 위치정보요약DB 행은 X/Y가 비어 있어 `geom NOT NULL` 적재에서 제외한다.
- T-013d/T-014: SHP 보조 로더는 ADR-012 대상 9개 레이어만 load plan으로 만들며, GDAL Python binding은 실제 호출 시에만 import한다. delta merge는 `settings.mvm_res_code_actions` 또는 DB `load_codes`에서 온 action map을 받도록 설계했다.
- T-017: epost 보조 우편번호용 `postal_pobox`, `postal_bulk_delivery` COPY 로더를 추가했다.

**실제 파일 검증**:
- `data/juso/202603_도로명주소 한글_전체분/rnaddrkor_seoul.txt` 첫 25행을 실제 CP949로 읽어 `bd_mgt_sn`, `rncode_full`, 건물번호, 우편번호, PNU 매핑을 검증했다.
- `data/juso/202604_위치정보요약DB_전체분.zip`의 `entrc_seoul.txt` ZIP member를 직접 스트리밍해 `sig_cd`, `ent_man_no`, `rncode_full`, `ent_se_cd`, EPSG:5179 X/Y를 검증했다.
- `data/juso/202604_내비게이션용DB_전체분/match_build_seoul.txt`와 `match_rs_entrc.txt`를 읽어 centroid/진입점 좌표와 kind 매핑을 검증했다.
- `data/juso/도로명주소 전자지도/강원특별자치도`의 SHP/DBF 파일로 ADR-012 보조 9개 레이어 load plan을 검증했다.
- 로컬 PostgreSQL(PostGIS)에서 `kor_travel_geo_codex_t017` 테스트 DB를 생성해 DDL 적용 → 실제 파일 샘플 COPY 적재 → `resolve_text_geometry_links()` → `mv_geocode_target` 생성까지 통과 확인 후 DB를 삭제했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 43 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_t017' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**:
- T-018 CLI를 운영 워크플로 수준으로 완성한다. 이번 작업에서 `load juso/locsum/navi`, `refresh mv`, `validate consistency`, `jobs` 기본 명령은 추가했지만 `load all-sidos`, `load shp-all`, `load epost`, 업로드 batch CLI는 후속이다.
- T-020 OpenAPI export 전에 FastAPI optional extra가 설치되지 않은 환경의 import 실패 정책을 정리한다.

---

## 2026-05-23 (claude, 텍스트 정본 + SHP polygon 하이브리드 전환)

**작업**: ADR-005를 부분 supersede하고 ADR-012(텍스트 정본 1차 + SHP polygon 보조 하이브리드), ADR-016(적재 진행도/정합성 API), ADR-007 복원·재정의를 묶어 사양 단계에서 전환. 사용자 지시: NTFS의 `data/juso` 텍스트 자료 3종(도로명주소 한글_전체분, 위치정보요약DB_전체분, 내비게이션용DB_전체분) 활용으로 완성도 ↑.

**변경 파일**:
- `docs/decisions.md` — ADR-005에 partial supersede 표시 / ADR-007 복원(위치정보요약DB ent_se_cd 기반) / ADR-012 신규 / ADR-016 신규
- `docs/data-model.md` — 마스터 14개 구조로 전면 재작성. 텍스트 1차 4종(`tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc`)과 SHP polygon 7종으로 분리. 텍스트 파일 포맷·컬럼 매핑 명시. MV 정의를 텍스트 정본 + 대표 출입구 + centroid fallback + `pt_source` 컬럼으로 재정의. 정합성 케이스 C1~C10 분류표와 `load_consistency_reports` 테이블 추가.
- `docs/backend-package.md` §9 — `loaders/text/`, `loaders/shp/`, `loaders/consistency.py` 분리. `juso_hangul_loader.py` 구현 예시(stdlib csv + `psycopg.copy()`, 인코딩 감지, 진행률 callback). `tl_spbd_buld_polygon` 분리 적재 전략. §9.8(진행도 API), §9.9(정합성 API), §9.10(로그/리포트 정책) 신규.
- `docs/backend-package.md` §10 CLI — `ktgctl load juso/locsum/navi/shp`, `ktgctl validate consistency`, `ktgctl jobs list/status/cancel` 추가.
- `docs/tasks.md` — T-006(18개 테이블), T-007(MV 재정의), T-011(`AsyncAddressClient` 진행도 API), T-013을 T-013a~d로 분할. T-026(정합성 검증) 신규.
- `docs/resume.md` — ADR 확인 목록 갱신 (~ADR-016).
- `CHANGELOG.md` — 정책 전환 기록.

**결정**:
- ADR-012: 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드. GDAL은 polygon 적재에만 사용. ADR-005의 GDAL Python binding 결정은 partial supersede.
- ADR-007 재정의: 대표 출입구 선택은 위치정보요약DB의 `ent_se_cd='0'` 기반. 출입구가 0개인 건물은 내비게이션용DB centroid fallback (MV의 `pt_source` 컬럼으로 출처 노출).
- ADR-016: 적재 진행도(`load_status`/`list_load_jobs`/`submit_load`/`cancel_load`)와 정합성 리포트(`run_consistency_check`/`consistency_report`)를 라이브러리·REST·디버그 UI에 일급으로 노출. C1~C10 케이스를 `load_consistency_reports` JSONB로 영속화.
- MV `mv_geocode_target` 컬럼명: `ent_pt_5179` → `pt_5179`, `ent_pt_4326` → `pt_4326` + `pt_source ∈ {entrance, centroid}` 추가.
- PNU 매핑(`mntn_yn 0→1, 1→2`, ADR-010)을 `tl_juso_text.pnu` generated stored column으로 박음.

**검증**: 문서 전용 변경. T-013a~T-013d(텍스트/SHP 분리 로더), T-026(정합성) 구현 시 reference.

**다음**: T-005 (`infra/engine.py`). 이후 T-006(DDL)부터 ADR-012의 14개 테이블 구조로 진행.

---

## 2026-05-23 (claude, 사양 리뷰 종합 반영)

**작업**: 두 차례 리뷰 의견(v1 기반 5건 + master 기반 5건)에 사용자 보완을 더해 사양 단계에서 미리 묶어 반영.

**변경 파일**:
- `SKILL.md` — §4 DO NOT 11~13 추가: (11) 공간 술어 형변환 금지·반경은 5179 meter, (12) bulk param 한도, (13) 작업 큐 영속화.
- `docs/data-model.md` — MV에 `idx_mv_geom5179` 추가 / "MV 갱신 모드" 절 (평시 CONCURRENTLY vs 분기 shadow MV swap, lock_timeout/인덱스 이름/권한/prepared statement invalidation 주의) / "공간 쿼리 가이드" (5179 meter 기준 CTE 예시, ent_pt_4326 응답 전용) / 행정 polygon 4326 변환 view (`v_kodis_bas_4326`, `v_scco_emd_4326`) / "PNU 조립" (mntn_yn 0/1 → 1/2, infra/generated column 위치) / "MVM_RES_CD 한 배치당 PK 단일화 가정" + 깨질 시 dedup CTE.
- `docs/architecture.md` — "적재 ↔ 서빙 단일 스키마 + MV" 강조 절.
- `docs/backend-package.md` §7.1 — engine factory DSN 보정 제거, settings.pg_dsn 신뢰. §9.7 — `load_jobs` 영속 테이블, lifespan recovery, advisory lock + FOR UPDATE SKIP LOCKED 패턴.
- `docs/decisions.md` — ADR-010(PNU 매핑 + 조립 위치 infra), ADR-011(작업 큐 `load_jobs` 영속화 + 다중 워커 안전성).
- `docs/tasks.md` — T-006/T-007/T-015에 본 ADR 인용.
- `docs/resume.md` — ADR 확인 목록 갱신.
- `CHANGELOG.md` — 정책 변경 기록.

**결정**:
- ADR-010: PNU 11번째 자리 매핑은 `0→1, 1→2`. 조립은 `infra/`(또는 generated stored column). `core/`는 의미론적 `mntn_yn`만 보관.
- ADR-011: `load_jobs` 별도 테이블에 작업 상태 영속화. lifespan startup에서 잔존 running→failed, queued는 payload 존재 여부에 따라 재큐잉/failed. 다중 워커 안전성은 `pg_try_advisory_lock` + `FOR UPDATE SKIP LOCKED`.
- 공간 쿼리: 반경/nearest는 5179(meter) 기준, 4326은 응답 전용. 술어 안에 `ST_Transform(t.geom, ...)` 금지.
- MV 갱신: 평시 CONCURRENTLY, 분기 풀로드는 shadow MV + RENAME swap (lock_timeout, prepared plan invalidation 명시).

**참고**: 본 변경은 모두 문서/사양 보강이며 코드 변경 없음. T-006/T-007/T-013/T-015 진행 시 본 ADR과 가이드를 reference로 적용.

**다음**: T-005 (`infra/engine.py`). 사양상 settings.pg_dsn을 그대로 신뢰하므로 구현 비용이 줄어듦.

---

## 2026-05-23 (codex, T-004 + 실제 SHP/DBF 검사)

**작업**: T-004 DTO 6종 구현 및 `data/juso/도로명주소 전자지도` 실제 파일 읽기 테스트 추가

**변경 파일**:
- 신규: `src/kortravelgeo/dto/geocode.py`, `src/kortravelgeo/dto/reverse.py`, `src/kortravelgeo/dto/search.py`, `src/kortravelgeo/dto/zipcode.py`, `src/kortravelgeo/dto/pobox.py`, `src/kortravelgeo/dto/admin.py`
- 신규: `src/kortravelgeo/loaders/juso_map.py`
- 신규: `tests/unit/test_dto_geocode.py`, `tests/unit/test_dto_reverse.py`, `tests/unit/test_dto_search_zipcode_pobox_admin.py`
- 신규: `tests/integration/test_juso_map_files.py`
- 갱신: `src/kortravelgeo/dto/__init__.py`, `pyproject.toml`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`

**결정**:
- DTO는 `docs/backend-package.md` §4의 wire contract를 우선해 pydantic v2 frozen model로 작성했다.
- `type` 필드는 vworld/API wire field이므로 DTO 파일별로 `A003` ruff ignore를 한정 적용했다.
- pydantic runtime이 nested DTO 타입을 해석해야 하므로 `GeocodeResponse`, `ReverseResultItem`, `SearchResultItem`의 address DTO imports는 runtime import로 유지하고 해당 파일에만 `TC001` ignore를 한정 적용했다.
- GDAL 적재 구현은 T-013 범위로 남긴다. 다만 이번 작업에서 순수 Python으로 SHP/DBF 헤더를 직접 열어 `강원특별자치도/51000`의 11개 마스터 레이어와 `TL_SPBD_BULD` 필드(`BD_MGT_SN`, `BULD_MNNM`, `MVM_RES_CD`, `RN_CD`, `SIG_CD` 등)를 검증했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 28 passed. 실제 파일 경로 `data/juso/도로명주소 전자지도/강원특별자치도/51000/*.shp|*.dbf|*.shx`를 열어 검사함.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**: T-005 — `infra/engine.py` async engine factory + 통합 테스트 준비.

---

## 2026-05-23 (claude, epost 데이터셋 정책)

**작업**: 우편번호 외부 API 활용 정책을 ADR-009로 확정하고 관련 문서 보강.

**변경 파일**:
- `docs/decisions.md` — ADR-009 추가 (epost 15000302, `downloadKnd=1` 분기 1회 전체 적재. 실시간 lookup 15056971 미도입).
- `docs/external-apis.md` — epost 절 보강: 데이터셋 ID 15000302, `downloadKnd` 4종 표, 분기 1회 전체 적재 흐름, 미도입 API(15056971) 명시. 한눈에 표에도 데이터셋 ID + ADR 인용.
- `docs/data-model.md` — `postal_pobox`/`postal_bulk_delivery` 위에 epost 15000302 ZIP 적재 출처와 ADR-009 인용.
- `.env.example` — `KTG_EPOST_API_KEY` 위 주석에 데이터셋 ID + ADR-009 표기.
- `CHANGELOG.md` — `### Added`에 ADR-009 요약.

**결정**:
- ADR-009: 우편번호 매칭은 epost 데이터셋 15000302의 전체 ZIP(`downloadKnd=1`)을 **분기 1회** 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE → INSERT. 변경분 누적 미운영. 실시간 lookup API(데이터셋 15056971) 미도입.

**검증**:
- 본 실행 환경(원격 컨테이너)은 `openapi.epost.go.kr` 외부망이 차단되어 직접 호출은 못 했다. 데이터셋 ID와 `downloadKnd` 4종 정의는 공공데이터포털 검색 결과로 확정. 사용자 WSL 환경에서 키 재발급 후 `curl ... -G --data-urlencode "downloadKnd=1"`로 응답을 마지막 점검 권장.
- 사용자가 채팅에 노출한 서비스 키는 즉시 재발급(또는 활용중지) 권장. 본 PR/문서/`.env.example`에 평문 커밋 없음.

**다음**: T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 시 본 ADR을 reference로 적용. CLI에 `ktgctl load epost --kind=full` 같은 entry를 두고 운영은 systemd timer로 분기 트리거.

---

## 2026-05-23 (claude, GDAL 셋업 문서)

**작업**: PR #3 마무리 — GDAL 시스템 의존성을 문서로 못박는다.

**변경 파일**:
- 신규: `docs/dev-environment.md` (WSL ext4 기준 셋업, conda/Docker 대안)
- 갱신: `docs/geocoding-readiness.md` (체크리스트 0번 항목 — 시스템 GDAL 설치)
- 갱신: `docs/resume.md` ("알려진 함정"에 GDAL 버전 미스매치, `libgdal-dev` 누락)
- 갱신: `SKILL.md` §2 (빠른 시작에 `apt install libgdal-dev` + `gdal==$(gdal-config --version)` 핀 추가)
- 갱신: `pyproject.toml` (`loaders` extra 위 주석 — 시스템 의존성/Docker 권장)
- 갱신: `docs/decisions.md` (ADR-008 — 시스템 GDAL과 동일 버전 핀)

**결정**:
- ADR-008: `loaders` extra는 `pip install "gdal==$(gdal-config --version)"`로 시스템과 동일 버전 핀. 운영·CI는 `osgeo/gdal:*` Docker 베이스 표준화. ADR-005 보강.

**검증**: 문서 전용 변경이라 코드 테스트 영향 없음. T-013 진행 시 실제 GDAL 환경에서 `dev-environment.md` 절차로 재현 가능.

**다음**: T-004 (DTO 6종).

---

## 2026-05-23 (codex, 리뷰 3차 반영)

**작업**: PR 리뷰 반영 — 설정 싱글톤 helper 역할 분리

**변경 파일**:
- 갱신: `src/kortravelgeo/settings.py`, `tests/unit/test_settings.py`, `docs/backend-package.md`

**결정**:
- `reset_settings()`는 인자 없이 싱글톤을 비우는 역할만 맡는다.
- 테스트나 명시 주입이 필요할 때는 `set_settings(settings)`를 사용한다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex, 리뷰 2차 반영)

**작업**: PR 리뷰 항목 5~10 반영 — DTO 필수성, validator 범위, CLI exit, ruff ignore, 예외명, namespace package 정리

**변경 파일**:
- 갱신: `src/kortravelgeo/dto/address.py`, `src/kortravelgeo/cli/main.py`, `src/kortravelgeo/exceptions.py`, `pyproject.toml`
- 갱신: `tests/unit/test_dto_address.py`, `tests/unit/test_exceptions.py`
- 갱신: `docs/backend-package.md`, `docs/decisions.md`
- 삭제: `src/kortravel/__init__.py`

**결정**:
- `RefinedAddress.structure`는 사양대로 필수 `AddressStructure`로 둔다.
- 빈 문자열 → `None` 변환 validator는 optional address fields에만 적용하고, `level0`은 빈 문자열을 명시적으로 거부한다.
- `typer.Exit`는 인스턴스(`raise typer.Exit()`)로 raise한다.
- `N815` ruff ignore는 vworld 호환 필드가 있는 `dto/address.py`에만 한정한다.
- base 예외명은 `KorTravelGeoError`로 확정한다(ADR-014).
- `kortravel` parent는 PEP 420 implicit namespace package로 둔다(ADR-015).

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex)

**작업**: PR 리뷰 반영 — 설정 기본값을 사양과 맞추고 README에 법적·데이터 사용 한계 추가

**변경 파일**:
- 갱신: `src/kortravelgeo/settings.py`, `.env.example`, `tests/unit/test_settings.py`, `README.md`

**결정**:
- `epost_download_url` 기본값은 브라우저 다운로드 페이지가 아니라 공공데이터포털 OpenAPI endpoint(`http://openapi.epost.go.kr/postal/downloadAreaCodeService/downloadAreaCodeService/getAreaCodeInfo`)로 둔다.
- `pg_statement_timeout_ms` 기본값은 사양값 5초(`5000`)로 둔다. 별도 ADR 없이 사양에 맞춘다.
- `api_default_radius_m` 기본값은 역지오코딩 hit rate를 위해 사양값 `200`으로 둔다.
- `api_cors_origins` 기본값은 빈 tuple로 둔다. localhost 허용은 `.env` override에서만 명시한다.
- README에 MIT 라이선스가 코드/문서에만 적용되고 외부 데이터/API 응답은 각 제공처 약관을 따른다는 한계를 명시했다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-22 (codex)

**작업**: T-001~T-003 구현 — Python 패키지 스캐폴드, 설정, 공통/주소 DTO와 단위 테스트 추가

**변경 파일**:
- 신규: `pyproject.toml`, `.env.example`
- 신규: `src/kortravel/__init__.py`, `src/kortravelgeo/__init__.py`, `src/kortravelgeo/version.py`, `src/kortravelgeo/py.typed`
- 신규: `src/kortravelgeo/settings.py`, `src/kortravelgeo/exceptions.py`, `src/kortravelgeo/client.py`, `src/kortravelgeo/cli/main.py`
- 신규: `src/kortravelgeo/dto/common.py`, `src/kortravelgeo/dto/address.py`
- 신규: `tests/unit/test_settings.py`, `tests/unit/test_dto_common.py`, `tests/unit/test_dto_address.py`
- 갱신: `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`

**결정**:
- import-linter는 도구 제약상 `root_package = "kortravel"`와 `containers = ["kortravelgeo"]` 조합으로 설정한다. 이는 문서의 `kortravelgeo` 계층 계약과 같은 의미이며 실제 도구 실행이 통과하는 형태다.
- `AsyncAddressClient`와 CLI는 이번 범위에서 import/install 검증을 위한 자리표시자로만 둔다. 실제 지오코딩 기능은 T-010/T-011에서 구현한다.
- 사용자가 지정한 SHP 기준 경로 `data/juso/도로명주소 전자지도`를 확인했다. 강원도 샘플의 11개 DBF 필드는 문서의 마스터 레이어(`TL_SPBD_BULD`, `TL_SPBD_ENTRC`, `TL_SPRD_MANAGE` 등)와 맞는다.

**검증**:
- `pip install -e ".[dev]"` 통과
- `pip install -e ".[api,dev]"` 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 10 passed
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**참고**:
- 현재 작업 디렉토리가 `/mnt/f` NTFS 위라 문서의 WSL/NTFS 경고가 그대로 적용된다. 기본 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 시작 전 실패하므로 검증 시 Linux `/tmp`를 명시했다.
- `loaders` extra는 현재 환경에 `gdal-config`가 없어 설치 검증하지 않았다. T-013에서 GDAL Python binding 설치 환경과 함께 별도 검증한다.

**다음**: T-004 — 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`)와 단위 테스트 작성.

---

## 2026-05-22 (human, 추가 명시)

**작업**: 사용자 추가 지시 반영 — 프로젝트/패키지 식별자 정정, WSL/NTFS 개발 정책, 데이터 위치(NTFS의 `data/`) 명시

**변경 파일**:
- 갱신: `README.md`, `AGENTS.md`, `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/backend-package.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reflection-summary.md` 외 일괄 치환 대상 전부

**결정**:
- 식별자 통일: GitHub 저장소 = `kor-travel-geo`, Python import = `kortravelgeo`, CLI = `kor-travel-geo`, env prefix = `KTG_`, PostgreSQL DB = `kor_travel_geo`, 프론트엔드 패키지 = `kor-travel-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "kor-travel-geo"`, scripts `kor-travel-geo = "kortravelgeo.cli.main:app"`, importlinter `root_package = "kortravelgeo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kortravelgeo` 패키지의 PostgreSQL+PostGIS 재구현 + `kor-travel-geo-ui` 프론트엔드)을 master 문서에 반영

**변경 파일**:
- 신규: `SKILL.md`, `CHANGELOG.md`
- 신규 (`docs/`): `architecture.md`, `decisions.md`, `data-model.md`, `tasks.md`, `resume.md`, `journal.md`, `backend-package.md`, `frontend-package.md`, `agent-guide.md`, `external-apis.md`
- 갱신: `AGENTS.md`, `README.md`, `docs/address-db-schema.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/spatialite-vworld-implementation.md`
- 신규: `docs/reflection-summary.md` (반영 내용 요약)

**결정**:
- ADR-001 ~ ADR-006, ADR-013을 `docs/decisions.md`에 초기 기록
- 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 (ADR-003)
- 라이브러리 API는 async-only (ADR-002)
- 로더는 GDAL Python binding 사용, `ogr2ogr` subprocess 폐기 (ADR-005)

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kor-travel-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kortravelgeo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
