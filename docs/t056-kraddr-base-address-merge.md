# T-056: `python-kraddr-base` Address 부분 병합 + 외부 라이브러리 삭제

## 상태

- 상태: 설계 (구현 전)
- 대상 브랜치: `agent/<agent>-t056-*`
- 관련 ADR: ADR-035(예정)
- 사용자 RFC: 2026-05-27 — "python-kraddr-base의 Address 파트 병합, Address 코드에 대한 조합/분리 작업만 가져올 것. python-kraddr-base 라이브러리는 삭제할 예정임."

## 목적

같은 WSL ext4 환경에 있는 `~/dev/python-kraddr-base`는 한국 주소 도메인 공통 helper를 제공하는 별도 라이브러리다. `python-kraddr-geo`도 일부 표면에서 이 라이브러리에 의존할 가능성이 있다. 사용자 RFC에 따라 `python-kraddr-base`는 곧 삭제되므로, 이 저장소가 필요한 부분(Address 조합/분리 코드)을 흡수해 dependency를 끊는다.

병합 범위는 **주소 문자열의 조합(compose)과 분리(parse) 코드만**이다. 다른 부분(우편번호 API client, 외부 service wrapper 등)은 흡수하지 않는다.

## 사전 인벤토리 (필수)

본 task의 첫 단계는 `~/dev/python-kraddr-base`에서 실제 무엇을 가져올지 인벤토리를 만드는 것이다.

```bash
cd ~/dev/python-kraddr-base
git rev-parse HEAD               # 병합 기준 commit
git log --oneline -20            # 최근 변경 이력
find . -name "*.py" -path "*/address/*" | head -50
find . -name "*.py" | xargs grep -l "def parse_\|def compose_\|def normalize_\|class Address" 2>/dev/null
```

대상 후보:

- `kraddr.base.address.parser` — 도로명/지번 주소 문자열을 구성 요소(시도/시군구/읍면동/리/도로명/건물번호/지번 본번/부번/상세주소)로 분리.
- `kraddr.base.address.composer` — 구성 요소를 표준 도로명/지번 문자열로 재조합.
- `kraddr.base.address.types` — Address dataclass/NamedTuple, 정규화 정책 상수.
- `kraddr.base.address.normalize` — 공백, 한자, 별표, 약어 정규화.

병합 제외:

- `kraddr.base.api.*` — 외부 API client.
- `kraddr.base.io.*` — 파일/DB I/O helper.
- `kraddr.base.cli.*` — CLI wrapper.
- 우편번호 helper(이미 `python-kraddr-geo`에 `epost` 어댑터 있음).

인벤토리 결과는 본 문서의 "병합 대상 파일" 섹션에 표로 추가한다.

## 흡수 위치

현재 `python-kraddr-geo`의 주소 정규화는 `src/kraddr/geo/core/normalize.py`에 있다. T-056에서는 신규 모듈을 만들지 않고 같은 위치에 흡수한다.

```
src/kraddr/geo/core/
├── normalize.py          # 기존
├── address/              # 신규 (T-056)
│   ├── __init__.py
│   ├── parser.py         # kraddr.base.address.parser에서 흡수
│   ├── composer.py       # kraddr.base.address.composer에서 흡수
│   ├── types.py          # Address dataclass, 정규화 상수
│   └── normalize.py      # 공백/한자/별표 정규화
```

`core.normalize`는 기존 export(parse_address 등)를 유지하되 내부 구현은 신규 `core.address.parser`를 호출하도록 thin shim으로 만든다. 하위 호환 보장.

```python
# core/normalize.py (after merge)
from kraddr.geo.core.address import parse_address as _parse_v2

def parse_address(query: str) -> ParsedAddress:
    """기존 API 유지. 내부는 T-056에서 흡수한 parser 사용."""
    return _parse_v2(query)
```

## 라이선스/저작권 확인

`~/dev/python-kraddr-base`의 LICENSE를 확인하고:

- MIT 또는 호환 라이선스면 코드 그대로 흡수 + LICENSE 보존.
- 같은 저작자(`digitie`)면 동일 저작권 표기.
- 흡수한 파일 최상단에 다음 주석 추가:

```python
# Adapted from python-kraddr-base (commit <SHA>, <date>)
# Original location: kraddr/base/address/parser.py
# Merged into python-kraddr-geo as T-056 (see docs/t056-kraddr-base-address-merge.md)
```

## 테스트 이관

`~/dev/python-kraddr-base/tests/`에서 Address 관련 단위 테스트만 가져온다.

- `test_address_parser.py`
- `test_address_composer.py`
- `test_address_normalize.py`
- 테스트 fixtures(예: `fixtures/addresses_real.json`)

가져온 테스트는 `tests/unit/core/test_address_*.py`로 rename하고 import path 수정. 통과 확인 후 commit.

## dependency 제거

```bash
# pyproject.toml에서 (있다면) 제거
grep -n "kraddr-base\|kraddr.base" pyproject.toml requirements*.txt
# import 검색
grep -rn "from kraddr.base\|import kraddr.base" src/ tests/ scripts/
```

발견된 import는 모두 `kraddr.geo.core.address.*`로 교체.

## 라이브러리 삭제 절차

`python-kraddr-base`는 본 task와 별도로 삭제된다. 본 PR에서는:

1. 본 저장소에서 dependency를 끊는다.
2. `python-kraddr-base`가 archive(GitHub archive 또는 read-only)로 전환되면 `docs/journal.md`에 archive URL과 마지막 commit SHA를 기록한다.
3. archive 시점까지는 본 저장소 ↔ `python-kraddr-base` 사이에 1-way 흡수만 일어난다. 양쪽에서 동시에 수정하지 않는다.

## 구현 순서

1. **인벤토리**: `~/dev/python-kraddr-base` HEAD SHA + 대상 파일 목록을 본 문서에 표로 기록.
2. **라이선스 확인**: LICENSE 명시 + 흡수 파일에 origin 주석.
3. **신규 모듈 생성**: `src/kraddr/geo/core/address/` 디렉터리 + 4개 파일(parser/composer/types/normalize).
4. **테스트 이관**: `tests/unit/core/test_address_*.py` 추가, fixtures 복사.
5. **shim 작성**: `core/normalize.py`가 신규 `core.address`를 호출하도록.
6. **import 정리**: 본 저장소에서 `from kraddr.base.*` 모두 제거.
7. **회귀 확인**:
   - `pytest -q` 전체 통과.
   - 기존 `parse_address` 동작이 흡수 전후 동일한지 fixture 비교.
   - `kraddr-geo` CLI smoke test.
   - frontend `npm run test` 통과(주소 정규화 사용 화면).
8. **journal/CHANGELOG/resume 갱신**.
9. **`python-kraddr-base` archive 안내**: README에 "본 라이브러리는 `python-kraddr-geo` T-056에서 흡수됨" 명시(외부 라이브러리는 별도 작업).

## 검증 기준

- `grep -rn "kraddr.base" .` 결과 0건.
- `pytest -q` 통과 + 흡수 전후 응답 차이 없음(snapshot 비교).
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports` 통과.
- `pyproject.toml`에서 `kraddr-base` dependency 제거.
- `docs/backend-package.md`의 모듈 트리에 `core/address/` 추가.

## 남은 위험

- `python-kraddr-base` 코드 일부가 다른 외부 라이브러리(예: 우편번호 client)와 강한 의존성을 갖고 있다면 단순 흡수가 어렵다. parser/composer 모듈 안에서 그런 의존성을 발견하면 제거 또는 미흡수 결정.
- `python-kraddr-base`의 parser가 본 저장소의 PNU generated column 규칙(`mntn_yn 0→1, 1→2`)과 약간 다른 정규화를 갖고 있을 수 있다. 흡수 시점에 PNU 생성 규칙과 충돌하면 본 저장소 규칙을 우선한다(테스트로 검증).
- 흡수 후 `python-kraddr-base`에 bug fix가 들어오면 본 저장소는 자동으로 반영되지 않는다. archive 시점까지의 fix는 본 저장소에 cherry-pick.
- 라이선스 호환이 안 되면 본 task는 흡수 대신 본 저장소에서 처음부터 다시 작성한다.

## 관련 ADR/Task

- ADR-035(예정): `python-kraddr-base` Address 부분 흡수 + 외부 lib 의존성 제거 결정.
- ADR-010: PNU 생성 규칙. 흡수한 parser가 같은 규칙을 따르도록.
- T-052: v2 API의 주소 분리/조합 결과를 candidate `address` 필드로 노출.
