# T-056: `python-kraddr-base` Address 부분 정리 + 외부 라이브러리 삭제 대비

## 상태

- 상태: 구현 완료
- 대상 브랜치: `codex/t056-kraddr-base-address-merge`
- 관련 ADR: ADR-035
- 사용자 RFC: 2026-05-27 — "`python-kraddr-base`의 Address 파트 병합, Address 코드에 대한 조합/분리 작업만 가져올 것. `python-kraddr-base` 라이브러리는 삭제할 예정임."

## 목적

같은 WSL ext4 환경에 있는 `~/dev/python-kraddr-base`는 한국 주소 도메인 공통 helper를 제공하는 별도 라이브러리다. 사용자 RFC에 따라 `python-kraddr-base`는 곧 삭제 또는 archive될 수 있으므로, 이 저장소가 필요한 Address 코드 helper를 자체 보유하고 외부 dependency 위험을 없앤다.

이번 확인 결과 `python-kraddr-base`의 실제 Address 표면은 사전 문서의 예상과 달랐다. 도로명/지번 문자열 parser package가 아니라 `kraddr.base.addresses` 단일 모듈의 코드 식별자 DTO/정규화 helper였고, 라이선스는 `GPL-3.0-or-later`였다. 본 저장소는 MIT이므로 원본 코드를 복사하지 않고, 동일한 도메인 규칙을 본 저장소 안에서 clean-room으로 재구현했다.

## 2026-05-28 인벤토리

| 항목 | 결과 |
|------|------|
| 경로 | `/home/digitie/dev/python-kraddr-base` |
| Git 상태 | `.git` 없음. `git rev-parse HEAD`는 `fatal: not a git repository` |
| 패키지명/버전 | `python-kraddr-base` / `0.1.5` |
| 라이선스 | `GPL-3.0-or-later` |
| Address 구현 파일 | `src/kraddr/base/addresses.py` |
| Address 테스트 | `tests/test_addresses.py` |
| Address 구현 SHA256 | `9722efb389d9b95087f0a4bc8e16f808cc2338fdf87c599512993241d010b21f` |
| Address 테스트 SHA256 | `db39cf7340102c7cf48c807d6d242cc4ed5445097585126491323ba0de5e86d6` |
| 원본 코드 크기 | `addresses.py` 875 lines, `test_addresses.py` 160 lines |

### 실제 모듈 구조

사전 문서에서 예상했던 `kraddr.base.address.parser`, `kraddr.base.address.composer`, `kraddr.base.address.types`, `kraddr.base.address.normalize` package는 존재하지 않았다. 실제 후보는 다음 단일 모듈이었다.

- `src/kraddr/base/addresses.py`
  - 시군구/법정동/도로명관리번호/도로명주소관리번호 관련 DTO
  - `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`, `bdMgtSn` 계열 mapping helper
  - 건물 본번/부번, 지하 여부 flag 정규화
- `tests/test_addresses.py`
  - 코드 길이/계층/조합/검증 테스트

도로명/지번 문자열을 보수적으로 분해하는 로직은 이미 본 저장소의 `src/kraddr/geo/core/normalize.py`에 있고, 원본 패키지에는 별도 문자열 parser가 없었다. 따라서 `core.normalize.parse_address()`는 그대로 유지한다.

## 결정

T-056에서는 원본 파일을 이식하지 않고 다음만 구현했다.

```
src/kraddr/geo/core/address/
├── __init__.py
└── codes.py
```

주요 공개 helper:

- `SigunguCode`
- `LegalDongCode`
- `RoadNameCode`
- `RoadNameAddressCode`
- `AddressCodeSet`
- `normalize_sigungu_code()`
- `normalize_legal_dong_code()`
- `normalize_road_name_code()`
- `normalize_road_name_address_code()`
- `normalize_building_management_number()`
- `normalize_building_number()`
- `normalize_underground_flag()`
- `address_code_set_from_mapping()`
- `road_name_address_code_from_mapping()`

`infra/external_api.py`의 Juso fallback 좌표 API 호출은 이제 `address_code_set_from_mapping()`을 통해 `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`를 먼저 정규화한 뒤 호출한다. 이는 T-052의 provider adapter 분리 전 사전 정리이기도 하다.

## 라이선스 처리

원본은 GPL-3.0-or-later이고 본 저장소는 MIT이다. 따라서 다음 원칙을 지켰다.

- 원본 `addresses.py`와 테스트 파일을 복사하지 않았다.
- 새 모듈에는 "clean-room implementation"임을 명시했다.
- 원본 commit SHA 주석은 남기지 않았다. 원본이 Git checkout이 아니어서 commit 기준을 만들 수 없고, 코드도 adapted source가 아니기 때문이다.
- 향후 `python-kraddr-base`가 archive되면 `docs/journal.md`에 archive URL과 마지막 확인 가능한 release/tag 또는 파일 SHA256을 추가한다.

## 검증

이번 PR의 직접 검증 기준:

- `rg "from kraddr\\.base|import kraddr\\.base|kraddr-base" pyproject.toml src tests scripts`에서 dependency/import 0건. 문서상의 task 설명은 예외적으로 이 파일과 관련 ADR에만 남긴다.
- `tests/unit/core/test_address_codes.py`에서 코드 정규화/계층/조합/mapping helper를 검증한다.
- `tests/unit/test_external_api.py`에서 Juso 좌표 API 요청 파라미터가 정규화된 값으로 나가는지 검증한다.
- 전체 검증은 `pytest -q`, `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`로 수행한다.

## 후속

- T-052: v1/v2 API 분리와 kakao/naver provider adapter 설계에서 `core.address` helper를 재사용한다.
- T-053: Admin UI의 provider 호출/정합성 분석 화면에서 주소 코드 필터(`sigungu_code`, `legal_dong_code`, `road_name_code`)를 노출할 때 `core.address` helper의 정규화 규칙을 기준으로 삼는다.
- `python-kraddr-base` 자체 archive/read-only 전환은 별도 저장소 운영 작업이다. 본 저장소에서는 더 이상 dependency나 import를 추가하지 않는다.
