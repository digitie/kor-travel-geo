# ADR-035: `python-legacy-address-base`의 Address 코드 helper를 독립 구현하고 외부 라이브러리 의존성을 끊는다

- 상태: accepted (2026-05-28 구현 반영)
- 날짜: 2026-05-27, 2026-05-28 개정
- 결정자: 사용자 요청, claude, codex

## 컨텍스트

같은 WSL ext4 환경의 `~/dev/python-legacy-address-base`는 한국 주소 도메인 공통 helper(주소 조합/분리, 정규화, 외부 API client 등)를 제공해 왔다. 사용자 RFC에 따라 `python-legacy-address-base` 라이브러리는 archive 예정이다. 본 저장소 `kor-travel-geo`는 이 라이브러리에 명시·암시적으로 의존하는 표면이 있을 수 있으므로, 필요한 부분만 흡수해 외부 dependency를 제거해야 한다.

2026-05-28 인벤토리 결과, `~/dev/python-legacy-address-base`는 Git checkout이 아니었고(`.git` 없음), license는 `GPL-3.0-or-later`였다. 사전 예상과 달리 `legacy.address_base.address.parser/composer/types/normalize` package는 없고, 실제 Address 표면은 `src/legacy/address-base/addresses.py` 단일 파일의 시군구/법정동/도로명관리번호/도로명주소관리번호 DTO와 mapping helper였다. 본 저장소는 MIT이므로 GPL 원본 코드를 직접 복사할 수 없다.

2026-05-28 사용자 확인에 따라 "Address 코드에 대한 조합/분리"는 주소 문자열 parser/composer가 아니라 코드 식별자의 조합·분해·정규화를 뜻하는 것으로 확정한다.

## 결정

`python-legacy-address-base` 원본 코드는 복사하지 않고, 본 저장소에 필요한 Address 코드 정규화/조합 helper만 `src/kortravelgeo/core/address/`에 공개 주소 코드 규칙 기반 독립 구현으로 둔다.

- 구현 대상: `SigunguCode`, `LegalDongCode`, `RoadNameCode`, `RoadNameAddressCode`, `AddressCodeSet`, `admCd`/`rnMgtSn`/`bdMgtSn` 계열 mapping helper.
- 기존 `core/normalize.py`의 도로명/지번 문자열 parser는 유지한다. 원본 패키지에 별도 문자열 parser가 없었기 때문이다.
- `infra/external_api.py`의 Juso fallback 좌표 API 호출은 새 `core.address` helper로 파라미터를 정규화한다.
- 원본 코드/테스트를 복사하지 않았으므로 origin 주석이나 원본 commit 주석을 추가하지 않는다. 원본은 Git checkout이 아니어서 기준 commit도 없다.
- 본 저장소의 `pyproject.toml`/`requirements*.txt`에는 `legacy-address-base` dependency를 추가하지 않고, `from legacy.address_base.*` import도 두지 않는다.

## 근거

- `python-legacy-address-base`는 곧 archive되므로, 본 저장소가 의존하면 빌드/CI/배포 위험이 발생한다.
- Address 코드 조합/분리는 본 저장소의 PNU generated column 규칙(ADR-010)과 직접 맞물려 있어 같은 저장소에서 관리하는 것이 정합성에 좋다.
- 라이브러리 분리를 유지하기에는 본 저장소가 유일한 consumer일 가능성이 높다.
- GPL 원본을 MIT 저장소에 직접 복사하면 라이선스가 오염된다. 공개 주소 코드 규칙 기반 독립 구현이면 라이선스와 유지보수 경계를 둘 다 지킬 수 있다.

## 결과

- T-056에서 `core.address` helper와 단위 테스트를 추가했다.
- Juso 외부 fallback은 좌표 API 호출 전에 주소 코드 파라미터를 정규화한다.
- 흡수 완료 후 `python-legacy-address-base`는 read-only archive로 전환하고, journal에 archive URL과 마지막 확인 가능한 release/tag 또는 파일 SHA256을 남긴다.
- T-052/T-053은 이 helper를 provider adapter와 admin 필터 정규화의 선행 기반으로 사용한다.

## 남은 위험

- `RoadNameAddressCode`는 26자리 도로명주소관리번호 자체만으로는 `admCd`의 리 코드 2자리를 복원할 수 없다. 외부 Juso 좌표 API 요청처럼 full `admCd`가 필요한 경로는 `AddressCodeSet`처럼 원본 `admCd`를 함께 보존하는 helper를 사용한다. 필수 코드가 없으면 fallback adapter는 좌표 API를 호출하지 않고 local `NOT_FOUND` 흐름으로 돌아간다.
- archive 시점 이후 외부에서 fix가 들어오면 본 저장소는 자동 반영하지 않는다. 별도 PR로 재구현 여부를 판단한다.
