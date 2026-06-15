# T-216 라이브 수용 후속

T-216은 T-126 phase ② 수용 후속에서 남아 있던 두 라이브 항목을 닫기 위한 실행 기록이다.

1. C11~C17 optional source를 RustFS/source registry에 등록하고 `custom` source match set으로 run-validation을 실행한다.
2. T-214와 같은 REST corpus 표본으로 c64 latency를 재측정한다.

## 기준

| 항목 | 값 |
|------|----|
| 기준 DB | `kor_travel_geo_t213_20260615_r3` |
| 기준 active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| 기준 source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| RustFS endpoint | `http://127.0.0.1:12101` |
| RustFS bucket/prefix | `kor-travel-geo` / `kor-travel-geo/t216/20260615-r2` |
| 산출물 root | `F:\dev\geodata\t216-acceptance\20260615-r2\` |

기본 `.env`가 가리키는 `kor_travel_geo`는 T-213 기준 DB가 아니므로 실행 wrapper에서 DB 이름만 `kor_travel_geo_t213_20260615_r3`로 명시 치환했다. secret 값은 artifact와 문서에 기록하지 않았다.

## source registry / run-validation

`scripts/run_t126_acceptance_followup.py --execute`를 WSL ext4 테스트 미러에서 실행했다. 입력 plan은 `F:\dev\geodata\juso\unused\`에서 optional source 8개 category, 40개 archive를 찾았다.

| 항목 | 결과 |
|------|------|
| run id | `20260615T093430Z` |
| base source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| custom source match set | `0c7d7ee7-75bf-4a1e-ae0b-015485e73656` |
| registered optional groups | 8개 |
| C11~C17 runnable/skipped/failed | `7 / 0 / 0` |
| quarantined group | 0개 |
| affected match set | 0개 |

등록된 group은 모두 `available` 경로로 들어갔다. 구조 검증 결과는 `warning`이며, 주요 원인은 일부 원천의 `.prj` 부재와 아직 상세 profile이 없는 optional single-file category다. 실패는 없다. 이 warning은 이번 run-validation의 presence/integrity gate를 막지 않았지만, optional category별 상세 구조 validator 강화는 T-127 후속으로 분리한다.

산출물:

- `F:\dev\geodata\t216-acceptance\20260615-r2\source-plan.json`
- `F:\dev\geodata\t216-acceptance\20260615-r2\registered-optional-groups.json`
- `F:\dev\geodata\t216-acceptance\20260615-r2\c11-c17-run-validation.json`
- `F:\dev\geodata\t216-acceptance\20260615-r2\summary.json`

## REST c64

처음 실행한 `rest-c64\`는 `--max-cases-per-sql`을 빠뜨려 REST case가 T-214 기준 425개가 아니라 1800개로 늘었다. 이 결과는 수용 판정에 쓰지 않고 exploratory artifact로만 보존한다.

수용 판정은 `rest-c64-425\`를 기준으로 한다.

| 항목 | 결과 |
|------|------|
| artifact | `F:\dev\geodata\t216-acceptance\20260615-r2\rest-c64-425\` |
| corpus SHA-256 | `3e832d5be6fcbe8f10f466fff54e051e77718e15e75936fa053dfebe3a91be65` |
| REST case count | 425 |
| measurements | 1,275 |
| concurrency | 64 |
| server profile | Python `3.13.14`, uvicorn worker `1`, `uvloop`, DB pool `20/64`, admission disabled, GeoIP gate off |
| active release 확인 | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| errors | 0 |
| worst c64 p95 | `Q4_SEARCH/search_hint=415.022ms` |
| T-214 기준 | `534.031ms` |
| 판정 | 수용 |

임시 API는 WSL 미러에서 `127.0.0.1:12518`에 띄우고 benchmark 후 종료했다. 기존 `127.0.0.1:12501` 서비스는 이 저장소가 관리하지 않으며, admin ops 조회가 500을 반환해 T-213 기준 서버로 사용하지 않았다.

## 코드 보정

실행 중 `source_member_scan`이 공급자 원본 SHP 파일명 `Total.JUSURB.20260501.TL_...11000.shp`를 전체 stem으로 인식해 optional shape bundle 구조 검증이 실패하는 문제를 확인했다. scanner가 알려진 layer명을 파일명 내부 token에서 추출하도록 보정했고, `TL_SPBD_ENTRC_DONG`이 `TL_SPBD_ENTRC`로 잘못 접히지 않도록 긴 layer명 우선 매칭을 적용했다.

PR #187 리뷰 후속으로 dot 전용 token 가정을 넓혀 underscore/hyphen/space 같은 구분자도 허용했다. 단, 구분자 없이 vendor prefix/date/layer/sido code가 완전히 붙은 파일명은 의도적으로 full-stem fallback으로 남긴다. 이 경우 구조 검증이 missing layer로 실패해 새 vendor 파일명 계약을 명시적으로 추가하게 한다.

## 검증

WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 확인했다.

```bash
.venv/bin/python -m pytest tests/unit/test_t203b_member_scan.py -q
.venv/bin/python -m ruff check src/kortravelgeo/infra/source_member_scan.py scripts/run_t126_acceptance_followup.py tests/unit/test_t203b_member_scan.py
.venv/bin/python -m mypy src/kortravelgeo/infra/source_member_scan.py scripts/run_t126_acceptance_followup.py
.venv/bin/lint-imports
.venv/bin/python -m pytest -q
```

결과는 focused unit `4 passed`, 전체 pytest `674 passed, 47 skipped`, ruff 통과, mypy 통과, import-linter `Layered architecture KEPT`다.
