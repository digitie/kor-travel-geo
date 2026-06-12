# T-043: PR #23~#41 리뷰 코멘트 audit/fixup

## 범위

2026-05-27 `main` 기준으로 PR #23부터 PR #41까지의 GitHub 리뷰 표면을 다시 읽었다. T-043 요구에 따라 단순 `gh pr view` 요약만 사용하지 않고 다음 표면을 함께 확인했다.

- PR conversation comment: GraphQL `pullRequest.comments`
- formal review body: GraphQL `pullRequest.reviews`
- inline review comment: REST `GET /repos/digitie/kor-travel-geo/pulls/{number}/comments`
- thread 상태: GraphQL `pullRequest.reviewThreads`

수집 원자료는 로컬 임시 파일 `/tmp/t043-pr23-41-review-surface.json`에 저장했다. 이 파일은 작업 재현용이며 git에는 포함하지 않는다.

## 전체 결과

| PR | 상태 | comment/review/thread | 판단 |
|----|------|-----------------------|------|
| #23 T-036 maplibre-vworld main 동기화 | merged | conversation 1, thread 0 | L1/L2/L5/L6을 이번 PR에서 반영. changelog release 정리는 릴리스 시점 작업으로 보류 |
| #24 PR20~#22 리뷰 후속 | merged | conversation 1, thread 0 | MV benchmark metadata 해석 가이드 일부를 이번 PR에서 반영. TypeAlias/metadata shape 등은 성능/UX 후속으로 보류 |
| #25 T-028 daily juso delta | merged | conversation 1, thread 0 | 신규 `MVM_RES_CD` 대응, dedup 정렬 전제, `No Data`, `--limit-per-file`, checksum/MV refresh 설명을 반영 |
| #26 T-029 보조 지번 모델 결정 | merged | conversation 1, thread 0 | 핵심 M1/L2/L3/L4는 T-038에서 이미 반영. 검색 ranking은 후속 지번 검색 확장 ADR로 보류 |
| #27 T-030 별도 도형/출입구 자료 검토 | merged | conversation 1, thread 0 | T-039~T-041 및 T-045 source set 설계로 대부분 해소. C10 family 정책은 T-045에서 이어서 다룸 |
| #28 T-038 parcel link loader | merged | conversation 1, thread 0 | 6종 child migration note를 이번 PR에서 반영. 검색 연결/ranking은 후속 성능·검색 task로 보류 |
| #29 T-039 roadaddr entrance loader | merged | conversation 1, thread 0 | MV stale warning은 T-049/T-027 운영 gate와 함께 다루는 것이 안전. `serving_entrc` 확장성은 T-047 쿼리 튜닝 후보 |
| #30 T-040 building shape bundle 비교 | merged | conversation 1, thread 0 | monthly monitoring과 후보 table trigger는 T-027/T-047 측정 산출물에 포함 |
| #31 T-041 상세주소 동/구역 레이어 검토 | merged | conversation 1, thread 0 | 상세주소 동 활성화 정책은 후속 overlay/search 요구가 생길 때 다룸. `TL_SPPN_MAKAREA`는 T-042로 승격됨 |
| #32 T-037 SHP geometry staging 튜닝 | merged | formal review 1, thread 0 | staging advisory lock과 skip metric을 이번 PR에서 반영. full truncate 보호/swap형 적재는 T-027/T-047 이후 큰 튜닝 후보 |
| #33 T-041 후속 `TL_SPPN_MAKAREA` 문서 | merged | conversation 1, thread 0 | ADR-027 남은 위험과 Polygon→MultiPolygon 변환 원칙을 이번 PR에서 반영. 1차 출처/응답 schema/parser는 T-042 진입 조건 |
| #34 T-043 task 등록 | merged | 없음 | 추가 조치 없음 |
| #35 VWorld/source set task 문서 | merged | 없음 | T-045/T-044에서 실행 |
| #36 T-046 backup/restore 설계 | merged | 없음 | T-046에서 구현 |
| #37 T-047 query performance 설계 | merged | 없음 | T-047에서 구현 및 상세 tuning 기록 |
| #38 maplibre-vworld 최신 동기화 | merged | 없음 | T-044에서 최신 upstream 재확인 후 wrapper 전환 |
| #39 ops metadata ADR | merged | 없음 | T-049에서 구현 |
| #40 README 법적 고지 | merged | 없음 | 추가 조치 없음 |
| #41 문서 정합성/task 순서 | merged | 없음 | 추가 조치 없음 |

GraphQL `reviewThreads` 기준 unresolved thread는 모든 대상 PR에서 0개였다. 즉 이번 T-043은 unresolved inline thread 해결이 아니라, merge 후 남은 top-level review follow-up을 문서/소규모 코드로 수렴하는 작업이다.

## 이번 PR에서 직접 반영한 항목

### PR #23

- `kor-travel-geo-ui/lib/vworld.ts`의 `redactVWorldTileUrl` alias에 수명 정책 주석을 추가했다. T-044에서 `redactVWorldUrl`로 호출자를 옮긴 뒤 제거한다.
- `kor-travel-geo-ui/tests/unit/vworld.test.ts`에 API key 누설 방지 assert를 추가했다. marker 문자열은 기존처럼 고정하되, 실제 보안 의도인 key 미포함도 함께 검증한다.
- `kor-travel-geo-ui/README.md` 검증 섹션에 WSL ext4에서는 Linux Node/npm을 사용하라는 경고를 추가했다.
- `docs/t036-maplibre-vworld-sync.md`에 `c91c9f3`가 stable tag가 아니라 `git ls-remote`로 확인한 upstream `main` 직접 커밋임을 기록했다.

### PR #24

- `docs/t035-mv-refresh-benchmark.md`에 `concurrent_sessions_before/after`가 `idle in transaction`을 의도적으로 포함한다는 설명을 추가했다.
- 같은 문서에 `wait_events_before/after`가 `pg_stat_activity` 전체 wait event snapshot이며, 정상 idle backend의 `Client:ClientRead`도 들어올 수 있음을 명시했다.

### PR #25

- `docs/t028-daily-juso-delta.md`에 신규 `MVM_RES_CD` 대응 절차를 추가했다.
- daily batch dedup에서 `source_file DESC`가 현재 파일명 형식에 의존하는 보조 정렬 키임을 명시했다.
- `No Data` 처리는 크기만 보고 skip하지 않고 decoded sentinel이 정확히 `No Data`인지 비교한다는 설명을 추가했다.
- `--limit-per-file` 사용 시 CLI stderr 경고를 출력하도록 했다.
- daily delta의 queue 직렬화, 디렉터리 checksum 안정성, manifest 값의 의미, daily 후 MV refresh를 자동 수행하지 않는 이유를 문서화했다.

### PR #28

- `docs/t038-parcel-link-loader.md`에 `full_load_batch` 기본 child가 5종에서 6종으로 바뀐 점과 외부 CI/cron/API 호출자가 `juso_parcel_link_load`를 추가해야 한다는 migration note를 추가했다.

### PR #32

- `TL_SPBD_BULD` projection staging 경로에 session-level advisory lock을 추가했다. 같은 DB에서 두 CLI가 동시에 고정 staging table을 사용하려 하면 두 번째 작업은 즉시 `LoaderError`로 실패한다.
- staging row count와 운영 insert row count를 비교해 `bd_mgt_sn` 공백 또는 `geom IS NULL`로 skip된 행을 stdout에 남긴다.
- `docs/t037-shp-geometry-tuning.md`에 위 두 운영 안전장치를 기록했다.

### PR #33

- ADR-027에 원천 `Polygon`을 운영 `MultiPolygon`으로 통일하고 loader에서 `ST_Multi()` 또는 `PROMOTE_TO_MULTI`를 적용한다는 원칙을 추가했다.
- ADR-027에 "남은 위험" 섹션을 추가했다. T-042 구현 전 1차 사양 출처, reverse trigger, 응답 schema, 국가지점번호 parser/generator 표준 인용을 확인해야 한다.

## 후속 task로 이관한 항목

| 항목 | 이관 대상 | 이유 |
|------|-----------|------|
| `tl_juso_parcel_link` 검색 ranking/dedup 정책 | T-047 또는 별도 지번 검색 확장 ADR | 보조 지번을 serving query에 연결하면 latency와 중복 정책이 함께 바뀐다. 성능 benchmark와 함께 결정한다. |
| 별도 원천 기준월 C10 family 정책 | T-045 | source set UX에서 원천별 기준월을 first-class로 다룬 뒤 C10 severity를 정한다. |
| `refresh mv`의 MV 정의 hash/stale warning | T-049/T-027 | serving release metadata와 final clean load gate에서 MV definition/version을 함께 관리하는 편이 안전하다. |
| building shape bundle monthly monitoring | T-027/T-047 | 최종 클린 적재와 성능 튜닝에서 전수 measurement 산출물로 관리한다. |
| `TL_SPPN_MAKAREA` 1차 사양 인용, 응답 schema, parser/generator | T-042 | 국가지점번호 loader/query 구현의 진입 조건으로 둔다. |
| `TL_SPBD_BULD` full mode truncate 보호를 staging→swap형으로 변경 | T-027/T-047 이후 튜닝 | 구현 폭이 커서 이번 audit PR의 안전한 fixup 범위를 넘는다. 최종 full-load와 성능 자료를 보고 별도 PR로 진행한다. |

## 검증

이번 PR은 문서 fixup과 작은 코드 안전장치를 포함한다.

로컬에서 수행한 검증:

```bash
git diff --check
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m py_compile src/kortravelgeo/cli/main.py src/kortravelgeo/loaders/shp/polygons_loader.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports
```

프론트엔드 로컬 검증은 Linux Node가 PATH에 없어 실행하지 못했다. 현재 PATH에는 Windows `npm`만 잡히며, 실행 시 UNC 경로 오류와 `eslint` 미인식으로 실패한다. 이 저장소 문서 정책대로 Windows `npm`으로 WSL ext4 작업 디렉토리를 검증하지 않고, GitHub Actions의 frontend job에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 확인한다.
