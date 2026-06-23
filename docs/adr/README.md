# ADR — Architecture Decision Records

`kor-travel-geo` / `kor-travel-geo-ui`의 누적 ADR. 파일당 1개(`NNN-<slug>.md`)로 둔다. **다음 후보 = ADR-065.**

- ADR은 **프로그램 핵심 구조**(의존 계층·데이터/식별 모델·패키지/서비스 구조·REST 계약·
  운영 모델) 결정만 둔다. 도메인/ETL·taxonomy·알고리즘·process·운영 결정 중 해당 topic
  문서로 옮긴 것은 아래 표의 "→ 이관" 항목으로 표시한다(원 맥락은 이관 문서 + git history 보존).
- 순수 개발 규칙(금지·컨벤션·프로세스)은 ADR이 아니라 [`SKILL.md` §4](../../SKILL.md)에 둔다 —
  아래 표의 "→ 개발 규칙" 항목. 옛 ADR 파일은 짧은 stub으로 남기고 규칙은 SKILL로 이관했다.
- 결정이 뒤집힐 때도 핵심 구조 ADR의 이전 기록은 지우지 않고 `superseded by ADR-XXX`로 표시해
  파일을 유지한다(superseded-but-informative). 고유 근거가 더는 없는 완전 중복 결정만 삭제한다 —
  아래 표의 `~~(삭제됨)~~` 항목(파일 제거, 삭제 이유 한 줄 기록).
- 각 ADR은 PR과 함께 커밋되어 코드/문서/결정이 동기된다.

## 목록

| ADR | 제목 | 위치 |
|-----|------|------|
| ADR-001 | PostgreSQL + PostGIS를 1차 저장소로 채택한다 | [001-postgres-postgis-primary-store.md](001-postgres-postgis-primary-store.md) |
| ADR-002 | 라이브러리 API는 async-only로 둔다 | → 개발 규칙 ([SKILL.md §4](../../SKILL.md) #2) |
| ADR-003 | 응답 구조는 vworld와 호환되도록 유지한다 | [003-vworld-compatible-response.md](003-vworld-compatible-response.md) |
| ADR-004 | ORM 위에 raw SQL Repository를 둔다 | [004-raw-sql-repository-over-orm.md](004-raw-sql-repository-over-orm.md) |
| ADR-005 | 로더는 `ogr2ogr` 대신 GDAL Python binding을 쓴다 | [005-gdal-python-binding-loader.md](005-gdal-python-binding-loader.md) (partially superseded by ADR-012) |
| ADR-006 | 적재 작업은 단일 인스턴스 in-process 큐로 직렬 처리한다 | [006-in-process-serial-load-queue.md](006-in-process-serial-load-queue.md) |
| ADR-007 | `mv_geocode_target`은 건물당 대표 출입구 1건만 보유한다 | [007-mv-geocode-target-one-entrance-per-building.md](007-mv-geocode-target-one-entrance-per-building.md) |
| ADR-008 | 로더 의존성은 시스템 GDAL과 동일 버전으로 핀한다 | → 개발 규칙 ([SKILL.md §4](../../SKILL.md) #15) |
| ADR-009 | 우편번호는 epost OpenAPI(15000302) ZIP을 분기 1회 전량 적재한다 | [009-epost-zip-quarterly-full-load.md](009-epost-zip-quarterly-full-load.md) |
| ADR-010 | PNU 토지구분 매핑은 infra 레이어에서 조립한다 | [010-pnu-land-class-mapping-in-infra.md](010-pnu-land-class-mapping-in-infra.md) |
| ADR-011 | 적재 작업 큐 상태는 `load_jobs` 테이블로 영속화한다 | [011-load-jobs-table-persistence.md](011-load-jobs-table-persistence.md) |
| ADR-012 | 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드 | [012-text-canonical-plus-shp-polygon-hybrid.md](012-text-canonical-plus-shp-polygon-hybrid.md) |
| ADR-013 | 프론트엔드 UI는 내부망 전용, 애플리케이션 인증 없음 | [013-internal-only-ui-no-app-auth.md](013-internal-only-ui-no-app-auth.md) (superseded by ADR-064) |
| ADR-014 | 기본 예외명은 `KorTravelGeoError`로 둔다 | → 개발 규칙 ([SKILL.md §4](../../SKILL.md) #16) |
| ADR-015 | `kortravel`는 implicit namespace package로 둔다 | → 개발 규칙 ([SKILL.md §4](../../SKILL.md) #17) |
| ADR-016 | 적재 상태와 정합성 리포트는 라이브러리·API로 일급 노출한다 | [016-load-status-consistency-report-api.md](016-load-status-consistency-report-api.md) |
| ADR-017 | 전국 풀로드는 batch DAG + 정합성 게이트 통과 후 MV swap | [017-fullload-batch-dag-consistency-gate-mv-swap.md](017-fullload-batch-dag-consistency-gate-mv-swap.md) |
| ADR-018 | PostGIS 보조 extension은 `x_extension` 스키마에 격리한다 | [018-extensions-in-x-extension-schema.md](018-extensions-in-x-extension-schema.md) |
| ADR-019 | 프론트엔드 런타임은 Next.js 16을 보안 하한선으로 둔다 | [019-nextjs-16-security-floor.md](019-nextjs-16-security-floor.md) |
| ADR-020 | 디버그 UI 지도는 VWorld WMTS + MapLibre를 사용한다 | [020-vworld-wmts-maplibre-debug-map.md](020-vworld-wmts-maplibre-debug-map.md) (amended by ADR-028, ADR-032, ADR-063) |
| ADR-021 | 도로명주소 일변동 ZIP은 MST만 즉시 반영하고 LNBR은 manifest 기록 | [021-daily-juso-zip-mst-only-lnbr-manifest.md](021-daily-juso-zip-mst-only-lnbr-manifest.md) |
| ADR-022 | 보조 지번 원천은 1:N 링크 테이블로 모델링한다 | [022-secondary-jibun-one-to-many-link-table.md](022-secondary-jibun-one-to-many-link-table.md) |
| ADR-023 | 별도 도형/출입구 자료는 full-load 기본 경로에 즉시 섞지 않는다 | [023-separate-shape-entrance-data-split-candidates.md](023-separate-shape-entrance-data-split-candidates.md) |
| ADR-024 | `도로명주소 출입구 정보`는 별도 테이블 + same-month direct fallback | [024-roadaddr-entrance-table-same-month-fallback.md](024-roadaddr-entrance-table-same-month-fallback.md) |
| ADR-025 | `도로명주소 건물 도형` bundle은 별도 분석 후보로 둔다 | [025-roadaddr-building-shape-bundle-analysis-only.md](025-roadaddr-building-shape-bundle-analysis-only.md) |
| ADR-026 | 상세주소 동 도형·구역 추가 레이어는 별도 overlay/분석 후보로 둔다 | [026-detail-dong-and-area-layers-overlay-only.md](026-detail-dong-and-area-layers-overlay-only.md) (partially amended by ADR-027) |
| ADR-027 | `TL_SPPN_MAKAREA`는 국가지점번호 보조 지오코딩 데이터로 별도 적재 | [027-sppn-makarea-national-point-number-aux.md](027-sppn-makarea-national-point-number-aux.md) |
| ADR-028 | 디버그 UI 지도는 `maplibre-vworld-js` 최신 소비 + domain wrapper 경계화 | [028-maplibre-vworld-domain-wrapper-boundary.md](028-maplibre-vworld-domain-wrapper-boundary.md) (amended by ADR-032, ADR-063) |
| ADR-029 | 원천 기준월은 source set으로 명시하고 혼합 적재는 확인 절차 | [029-source-set-mixed-yyyymm-confirmation.md](029-source-set-mixed-yyyymm-confirmation.md) |
| ADR-030 | 적재 완료 DB 백업/복원은 병렬 directory dump + 압축 아카이브 | [030-db-backup-restore-directory-dump-tar-zst.md](030-db-backup-restore-directory-dump-tar-zst.md) |
| ADR-031 | 전국 적재 후 쿼리 성능은 반복 벤치마크로 gate + 보조 view/MV 허용 | [031-post-load-query-benchmark-gate-aux-mv.md](031-post-load-query-benchmark-gate-aux-mv.md) |
| ADR-032 | `maplibre-vworld-js`는 최신 소비, `kor-travel-geo` 특화 기능은 이 저장소 | [032-maplibre-vworld-latest-consume-domain-here.md](032-maplibre-vworld-latest-consume-domain-here.md) (dependency choice superseded by ADR-063) |
| ADR-033 | 운영 메타데이터는 `ops` 스키마 감사·스냅샷·릴리스 테이블로 관리 | [033-ops-schema-audit-snapshot-release.md](033-ops-schema-audit-snapshot-release.md) |
| ADR-034 | AI 에이전트는 고정 Git worktree + CodeGraph 인덱스를 사용한다 | [034-ai-agent-fixed-worktree-codegraph.md](034-ai-agent-fixed-worktree-codegraph.md) (superseded by ADR-041) |
| ADR-035 | Address 코드 helper를 독립 구현하고 외부 라이브러리 의존을 끊는다 | [035-address-code-helper-independent-impl.md](035-address-code-helper-independent-impl.md) |
| ADR-036 | DB Restore는 같은 cluster `ALTER DATABASE RENAME` hot-swap을 1차로 | [036-restore-hot-swap-alter-database-rename.md](036-restore-hot-swap-alter-database-rename.md) |
| ADR-037 | 외부 IP REST API는 대한민국 IP만 허용한다 (GeoIP gate) | [037-geoip-gate-korea-only-rest-api.md](037-geoip-gate-korea-only-rest-api.md) |
| ADR-038 | API 표면을 v1(vworld 호환)·v2(자체 통합 candidate)로 분리한다 | [038-api-v1-vworld-v2-candidate-split.md](038-api-v1-vworld-v2-candidate-split.md) |
| ADR-039 | Python 라이브러리는 후보 목록 API만 공개하고 `_v2` 접미사를 제거한다 | [039-python-library-candidate-api-drop-v2-suffix.md](039-python-library-candidate-api-drop-v2-suffix.md) |
| ADR-040 | ~~(삭제됨)~~ | 삭제 — PC/WSL 로컬 포트 15434/8888/13088 결정. ADR-042→045→046 거쳐 ADR-048로 완전 대체, 고유 근거 없음 |
| ADR-041 | NTFS main repo와 WSL ext4 테스트 미러를 사용한다 | [041-ntfs-main-repo-wsl-ext4-test-mirror.md](041-ntfs-main-repo-wsl-ext4-test-mirror.md) |
| ADR-042 | ~~(삭제됨)~~ | 삭제 — 로컬 포트 9001/9002 + Docker 점유자 정리 결정. ADR-046→048로 완전 대체된 중간 포트표 |
| ADR-043 | 행정구역 반경조회는 subdivided serving accelerator를 사용한다 | [043-region-radius-subdivided-accelerator.md](043-region-radius-subdivided-accelerator.md) |
| ADR-044 | 관리 UI 업로드 파일은 선택적으로 RustFS에 저장한다 | [044-admin-upload-optional-rustfs-storage.md](044-admin-upload-optional-rustfs-storage.md) (superseded by ADR-045) |
| ADR-045 | PostgreSQL과 RustFS는 외부 인프라로 두고 접속 설정만 저장한다 | [045-postgres-rustfs-external-infra.md](045-postgres-rustfs-external-infra.md) |
| ADR-046 | ~~(삭제됨)~~ | 삭제 — 로컬 포트 5432/12101/12201/12205 결정. ADR-048로 완전 대체된 중간 포트표 |
| ADR-047 | 프로젝트 식별자는 `kor-travel-geo` 계열로 통일한다 | [047-project-identifier-kor-travel-geo.md](047-project-identifier-kor-travel-geo.md) |
| ADR-048 | 로컬 API/UI 포트는 Docker 실행과 같은 12501/12505를 사용한다 | [048-local-ports-match-docker-12501-12505.md](048-local-ports-match-docker-12501-12505.md) |
| ADR-049 | T-109 원천 업로드·매칭·검증은 확장성 우선 설계로 구현한다 | [049-t109-source-upload-match-validate-design.md](049-t109-source-upload-match-validate-design.md) |
| ADR-050 | T-109 후속은 원천 보강 검증 먼저, 적재/백업 구현 다음 (T-번호·v1/v2 audit) | [050-t109-followup-order-numbering-v1-v2-audit.md](050-t109-followup-order-numbering-v1-v2-audit.md) |
| ADR-051 | 보강 출입구 source의 serving 좌표 ranking 편입은 별도 gate로 제한 | [051-c11-entrance-serving-promotion-gate.md](051-c11-entrance-serving-promotion-gate.md) (proposed; C11 validation-only 고정) |
| ADR-052 | RustFS 원천 archive는 자동 삭제 금지, 수동 관리 표면으로만 정리 | [052-rustfs-archive-no-auto-delete-manual-cleanup.md](052-rustfs-archive-no-auto-delete-manual-cleanup.md) |
| ADR-053 | REST v1 geocode/reverse는 VWorld HTTP envelope를 맞추고 `x_extension` 유지 | [053-v1-vworld-http-envelope-keep-x-extension.md](053-v1-vworld-http-envelope-keep-x-extension.md) |
| ADR-054 | optional 원천은 역할별 승격, 국가지점번호 좌표는 계산값 사용 | [054-optional-source-role-based-promotion.md](054-optional-source-role-based-promotion.md) |
| ADR-055 | C11 좌표 세부 출처는 `coord_source_detail`로 노출, `pt_source` enum 미확장 | [055-c11-coord-source-detail-no-pt-source-enum.md](055-c11-coord-source-detail-no-pt-source-enum.md) |
| ADR-056 | v2 후보 enum은 producer 의미로 좁히고 국가지점번호는 `grid_cell` 정밀도 | [056-v2-enum-narrowing-grid-cell-precision.md](056-v2-enum-narrowing-grid-cell-precision.md) |
| ADR-057 | v2 geocode producer는 tuple schema 안에서 후보 병합 + metadata dedup | [057-v2-geocode-candidate-merge-metadata-dedup.md](057-v2-geocode-candidate-merge-metadata-dedup.md) |
| ADR-058 | confidence는 중앙 모델로 고정, SPPN grid 후보는 exact 주소보다 낮게 | [058-central-confidence-model-sppn-grid-lower.md](058-central-confidence-model-sppn-grid-lower.md) |
| ADR-059 | T-144 성능 우선 API 계약은 기본값·상한 고정, 큰 breaking은 근거 시 분리 | [059-t144-performance-first-api-contract.md](059-t144-performance-first-api-contract.md) |
| ADR-060 | v2 API 컨벤션을 차원별로 명문화, 변경은 additive 우선·breaking 묶음 분리 | [060-v2-api-conventions-dimensions-additive-first.md](060-v2-api-conventions-dimensions-additive-first.md) |
| ADR-061 | 전역 RequestValidationError 핸들러는 전 경로 구조화 400 envelope로 통일 | [061-global-validation-error-structured-400-envelope.md](061-global-validation-error-structured-400-envelope.md) |
| ADR-062 | v2 breaking 묶음(enum 정직화·envelope/error 통일·좌표 lon/lat)을 배포 전 일괄 적용 | [062-v2-breaking-bundle-pre-deploy.md](062-v2-breaking-bundle-pre-deploy.md) |
| ADR-063 | 디버그 UI 지도는 GitHub `maplibre-vworld-react` 패키지를 소비한다 | [063-maplibre-vworld-react-github-map.md](063-maplibre-vworld-react-github-map.md) |
| ADR-064 | Admin UI 로그인과 공개 API key 관리를 둔다 | [064-ui-login-admin-proxy-public-api-keys.md](064-ui-login-admin-proxy-public-api-keys.md) |

## ADR 표준 형식

새 ADR은 다음 표준 형식을 따른다.

```
# ADR-NNN: <결정 요약>

- 상태: proposed | accepted | superseded by ADR-XXX
- 날짜: YYYY-MM-DD
- 결정자: <agent | human>

## 컨텍스트
<무엇이 문제였나. 어떤 제약·요구가 있었나.>

## 결정
<무엇을 정했는가. 한 문장으로.>

## 근거
-

## 결과(긍정)
-

## 결과(부정)
-

## 후속
- (open) 추가 검증 필요한 사항
```

기존 ADR을 뒤집을 때는 새 ADR을 추가하고, 옛 ADR의 상태를 `superseded by
ADR-XXX`로 표시한다 — 기존 본문은 지우지 않는다. 순수 개발 규칙이면 ADR 대신
[`SKILL.md` §4](../../SKILL.md)에 두고, 옛 ADR 파일은 stub으로 남긴다.
