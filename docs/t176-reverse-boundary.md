# T-176 reverse 경계·근접 정확도 정합

## 목적

T-176은 reverse geocode의 암묵 규약을 테스트와 문서로 고정한다. 대상은 `type="both"` fan-out, 거리 동률 정렬, `radius_m` 경계 포함 여부, 주소 후보가 없는 먼 좌표의 `OK`/`NOT_FOUND` 의미다.

## 결정

- Reverse 반경은 EPSG:5179 meter 좌표에서 `ST_DWithin(t.pt_5179, p.geom, :radius_m)`로 판정한다. PostGIS `ST_DWithin` 기준이므로 경계 거리 `distance_m == radius_m`도 포함한다.
- Recent-nearest SQL 정렬은 `t.pt_5179 <-> p.geom` KNN을 유지하되, 동률은 `distance_m ASC`, `pt_source='entrance'` 우선, `bd_mgt_sn`, `rncode_full`, `bjd_cd` 순으로 결정한다.
- `type="both"`는 SQL base row `limit`을 먼저 적용한 뒤, 각 base row를 `road`, `parcel` 순서로 fan-out한다. 따라서 내부 `limit=5`이면 v1/v2 후보는 주소 후보 기준 최대 10개가 될 수 있다.
- 주소 후보가 없더라도 입력 좌표가 국가지점번호 지원 envelope 안에 있으면 reverse 응답은 `OK`다. v1은 빈 `result`와 `x_extension.national_point_number`를 반환하고, v2는 `match_kind="sppn"` 후보를 반환한다.
- 주소 후보도 없고 국가지점번호 context도 만들 수 없으면 `NOT_FOUND`다. 한국 lon/lat bounds 밖 입력은 T-173 기준대로 `ERROR`/좌표 검증 오류다.

## 변경 파일

- `src/kortravelgeo/infra/reverse_repo.py`
  - `_NEAREST_SQL`에 deterministic tie-break `ORDER BY`를 추가했다.
- `tests/unit/test_t176_reverse_boundary.py`
  - SQL radius/tie-break 계약, `both` fan-out, context-only `OK`, true no-context `NOT_FOUND`, radius edge confidence를 검증한다.
- `tests/fixtures/geocoder_golden_corpus.json`
  - `T140-REV-BOUNDARY-001`을 road boundary assertion으로 좁혔다.
  - `T140-REV-SEA-001`을 `status_any` future seed에서 기본 live `OK`/SPPN context-only case로 승격했다.
- `docs/reverse-geocoding.md`, `docs/backend-package.md`, `docs/t140-geocoder-golden-corpus.md`
  - 위 규약과 corpus 상태를 문서화했다.

## 검증

Windows focused:

```bash
python -m pytest tests/unit/test_t176_reverse_boundary.py tests/unit/test_infra_repo_sql.py tests/unit/test_v2_api.py -q
python -m pytest tests/unit/test_t140_geocoder_golden_corpus.py -q
python scripts/run_geocoder_golden_corpus.py --mode fixture --run-id t176-fixture-smoke --output-dir artifacts/golden-corpus/t176-fixture-smoke
python -m ruff check src/kortravelgeo/infra/reverse_repo.py tests/unit/test_t176_reverse_boundary.py
```

결과:

- focused unit: `56 passed`
- T-140 corpus unit: `5 passed`
- fixture smoke: `25/25`, corpus SHA-256 `7db1b91c556e8fea22a05eda4a209d6c06925dacea287ff26e8eb47292173f83`

WSL ext4 mirror:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src/kortravelgeo
.venv/bin/lint-imports
.venv/bin/python scripts/export_openapi.py --check
```

결과:

- pytest: `914 passed, 54 skipped`
- ruff: 통과
- mypy: `Success: no issues found in 141 source files`
- import-linter: `Layered architecture KEPT`
- OpenAPI check: 통과

## CodeGraph

CodeGraph MCP `codegraph_context`는 이번 작업에서도 `Transport closed`로 실패했다. 대신 NTFS worktree에서 `codegraph sync`와 `codegraph status`를 실행했고, 인덱스 최신 상태를 확인했다.
