# T-175 region hint 정확도·교차검증

## 범위

T-175는 `sig_cd`/`bjd_cd` region hint가 geocode, reverse, search 경로에서 같은 의미로 적용되는지 고정한다. T-057에서 추가한 성능 hint 표면은 유지하되, 두 hint가 동시에 들어온 경우 서로 다른 지역을 가리키면 조용한 `NOT_FOUND`가 아니라 입력 오류로 처리한다.

## 결정

`RegionHint`의 유효 조합은 다음과 같다.

| 입력 | 판정 |
|------|------|
| `sig_cd=11` | 유효. 서울특별시 prefix |
| `sig_cd=11230` | 유효. 동대문구 시군구 코드 |
| `bjd_cd=11230107` | 유효. 법정동 8자리 prefix |
| `bjd_cd=1123010700` | 유효. 법정동 10자리 코드 |
| `sig_cd=11230`, `bjd_cd=1123010700` | 유효. `bjd_cd`가 `sig_cd`로 시작 |
| `sig_cd=11680`, `bjd_cd=1123010700` | 오류. 서로 다른 시군구 |

오류 응답은 기존 validation 계약을 따른다.

- v2와 `/v1/address/search`: HTTP 400 + `E0100`
- v1 VWorld 호환 `/v1/address/geocode`, `/v1/address/reverse`: HTTP 400 + `INVALID_TYPE`

## 구현

- `src/kortravelgeo/dto/region.py`
  - `validate_region_hint_consistency()`를 추가했다.
  - `RegionHint`가 `sig_cd`/`bjd_cd` prefix 일관성을 검증한다.
- `src/kortravelgeo/dto/v2.py`
  - `GeocodeV2Input`, `ReverseV2Input`, `SearchV2Input` 생성 시점에 같은 검증을 실행한다.
- Repository SQL은 바꾸지 않았다.
  - `geocode`, `search`, `reverse`, road geometry SQL이 모두 `sig_cd_filter`, `sig_cd_prefix`, `bjd_cd_filter`, `bjd_cd_prefix` bind를 가진다는 회귀 테스트만 추가했다.
- T-140 corpus를 25개로 확장했다.
  - `T140-GEO-ROAD-BJD-HINT-001`: `bjd_cd=1123010700` 단독 hint.
  - `T140-GEO-REGION-HINT-MISMATCH-001`: `sig_cd=11680` + `bjd_cd=1123010700` negative.

## 검증

Windows focused:

```bash
python -m pytest tests/unit/test_region_hint.py tests/unit/test_t175_region_hint_validation.py tests/unit/test_infra_repo_sql.py tests/unit/test_t140_geocoder_golden_corpus.py -q
python -m ruff check src/kortravelgeo/dto/region.py src/kortravelgeo/dto/v2.py tests/unit/test_region_hint.py tests/unit/test_t175_region_hint_validation.py tests/unit/test_infra_repo_sql.py
python scripts/run_geocoder_golden_corpus.py --mode fixture --run-id t175-fixture-smoke --output-dir artifacts/golden-corpus/t175-fixture-smoke
```

결과:

- pytest: 48 passed
- Ruff: 통과
- T-140 fixture smoke: 25/25 통과

WSL ext4 테스트 미러 전체 게이트:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src/kortravelgeo
.venv/bin/lint-imports
.venv/bin/python scripts/export_openapi.py --check
```

결과:

- pytest: 909 passed, 54 skipped
- Ruff: 통과
- mypy: 141 source files 통과
- import-linter: Layered architecture KEPT
- OpenAPI check: 통과

CodeGraph MCP는 이번 세션에서도 `Transport closed`로 실패했다. 대체로 `codegraph sync && codegraph status`를 실행했고, CLI 인덱스는 461 files / 9,080 nodes / 11,508 edges 최신 상태였다.

## 후속

T-176에서 reverse 경계·근접 정확도 규칙을 고정한다. T-175에서 추가한 region hint negative는 T-176/T-165 corpus slice와 함께 계속 회귀 기준으로 사용한다.
