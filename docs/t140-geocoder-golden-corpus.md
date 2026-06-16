# T-140 geocoder/reverse golden corpus

T-140은 정확도와 회귀 방지를 위한 고정 corpus와 실행 harness를 추가한다. 이 문서는
후속 T-142/T-143/T-165~T-176에서 같은 입력을 반복 검증하도록 확장한 corpus 상태를
기록한다.

## 산출물

| 항목 | 경로 |
|------|------|
| Corpus | `tests/fixtures/geocoder_golden_corpus.json` |
| Runner | `scripts/run_geocoder_golden_corpus.py` |
| 단위 테스트 | `tests/unit/test_t140_geocoder_golden_corpus.py` |
| Fixture artifact | `F:\dev\geodata\t140-geocoder-golden-corpus\20260616-r1\fixture\` |

## Corpus schema

최상위는 `schema_version=1`과 `cases[]`를 가진 JSON object다. 각 case는 다음 필드를 가진다.

| 필드 | 의미 |
|------|------|
| `case_id` | `T140-` prefix를 가진 안정 ID |
| `operation` | `geocode`, `reverse`, `search`, `zipcode`, `pobox` |
| `category` | 정확도 축(`road-exact`, `road-fuzzy`, `reverse-nearest` 등) |
| `params` | `AsyncAddressClient` public method에 넘길 입력 |
| `expected` | `status`, `status_any`, `min_results`, `fields`, `field_contains`, `numeric_lte`, `numeric_gte`, `contains_text`, `error_contains` |
| `golden_fields` | live 실행 artifact에 따로 기록할 응답 field path |
| `tags` | 기본 live 포함/제외와 후속 작업 routing용 태그 |
| `performance_budget_ms` | case 단위 smoke latency budget. 정식 고부하 budget은 T-141/T-163에서 고정 |

응답 hash는 runner가 `query_id` 같은 불안정 field를 제거한 뒤 SHA-256으로 기록한다. 따라서 같은 DB/코드/입력에서 candidate field가 바뀌면 artifact diff로 드러난다.

## 포함 범위

현재 corpus는 25개 case다.

| 축 | 대표 case |
|----|-----------|
| 도로명 exact | `T140-GEO-ROAD-EXACT-001` |
| region hint | `T140-GEO-ROAD-SIG-HINT-001`, `T140-GEO-ROAD-BJD-HINT-001`, `T140-GEO-REGION-HINT-MISMATCH-001` |
| 도로명 fuzzy/ranking | `T140-GEO-ROAD-FUZZY-001` |
| 정규화 변형 | `T140-GEO-WHITESPACE-ALIAS-001` |
| 지번 exact | `T140-GEO-PARCEL-EXACT-001` |
| 복합 시군구 suffix | `T140-GEO-SGG-SUFFIX-001` |
| reverse nearest/boundary | `T140-REV-NEAREST-001`, `T140-REV-BOUNDARY-001` |
| search/zipcode | `T140-SEARCH-ROAD-001`, `T140-ZIP-ADDRESS-001` |
| 국가지점번호 | `T140-GEO-SPPN-001`, `T140-REV-SPPN-001` |
| negative | `T140-NEG-GEOCODE-001`, `T140-NEG-REVERSE-001` |
| 후속 seed | 단독 행정구역, 건물명, 시군구용건물명, 사서함/다량배달처, 바다/도서/산지/동명이인 도로명 |

기본 live 실행은 `optional-source`, `future-followup` 태그를 제외한다. T-165 이후 `T140-GEO-WHITESPACE-ALIAS-001`은 `서울시`, 불규칙 공백, 괄호 노트, 전각 숫자·하이픈, 도로명-건물번호 무공백 입력에서도 `왕산로 189-4` road 후보와 `sig_cd=11230`을 반환해야 하는 기본 live 정규화 case다. T-171 이후 `T140-GEO-ROAD-FUZZY-001`은 기본 live에 포함되는 ranking case이며, 도로명 오타 입력에서도 같은 본번·부번 후보가 1순위인지 확인한다. T-172 이후 `T140-GEO-SPPN-001`은 국가지점번호 grid cell 후보 confidence `0.72`를 golden으로 고정한다. T-175 이후 region hint case는 `sig_cd` 단독, `bjd_cd` 단독, 모순 hint negative를 모두 포함한다. T-176 이후 `T140-REV-BOUNDARY-001`은 1순위 road 후보와 반경 포함을 확인하고, `T140-REV-SEA-001`은 주소 후보가 없는 먼 좌표의 SPPN context-only `OK` 의미를 기본 live case로 고정한다. epost 사서함/다량배달처와 아직 기대 field를 좁히지 않은 건물명/도서 seed는 fixture에는 남기되, 후속 task에서 OK 기준으로 승격한다.

## 실행

Fixture/schema 검증:

```bash
python scripts/run_geocoder_golden_corpus.py \
  --mode fixture \
  --run-id t140-fixture-20260616-r1 \
  --output-dir /mnt/f/dev/geodata/t140-geocoder-golden-corpus/20260616-r1/fixture
```

T-213 r3 live DB 검증 예시:

```bash
python scripts/run_geocoder_golden_corpus.py \
  --mode live \
  --pg-dsn "$KTG_PG_DSN" \
  --run-id t140-live-default-20260616-r1 \
  --output-dir /mnt/f/dev/geodata/t140-geocoder-golden-corpus/20260616-r1/live-default
```

`--include-default-skips`를 주면 `optional-source`/`future-followup`도 포함한다. 특정 후속 작업은 `--include-tag sppn` 또는 `--exclude-tag future-followup`처럼 태그로 slice를 고정할 수 있다.

## 이번 검증

Fixture run 결과:

- corpus SHA-256: `0b4ff00d1a59520da3237daf57c51e9be1e870a699976f1b86e1d48482d32b99`
- cases: `25`
- selected: `25`
- ok: `25`
- errors: `0`

Live mode는 runner 기능을 확인하기 위해 T-213 r3 DB명으로 시도했지만, 현재 세션의 WSL `.env`에 있는 `KTG_PG_DSN` credential이 로컬 PostgreSQL 인증과 맞지 않아 DB 접속 전 단계에서 실패했다. 따라서 이 PR의 pass artifact는 fixture/schema run으로 한정하고, live pass는 올바른 `KTG_PG_DSN`을 주입한 환경에서 위 명령으로 재실행한다. 이 blocker는 corpus/runner 동작과 분리된 로컬 credential 문제다.

## 후속 사용

- T-141/T-163: `performance_budget_ms`는 smoke budget으로만 쓰고, 고부하 p95/p99/error budget은 별도 matrix 결과로 고정한다.
- T-142: T-176에서 좁힌 reverse boundary/context-only case를 공간 조회 최적화 전후의 correctness gate로 재사용한다.
- T-165: `T140-GEO-WHITESPACE-ALIAS-001` expected field를 road 후보, `왕산로 189-4`, `sig_cd=11230`으로 좁혔다. T-171 fuzzy ranking case는 `ranking` 태그와 `numeric_gte` confidence 하한으로 승격됐고, T-172는 SPPN forward case에 `confidence` 태그와 고정 confidence field를 추가했다.
- T-166~T-168: 국가지점번호 case를 forward gate 분리와 reverse first-class code 방출의 회귀 기준으로 쓴다.
