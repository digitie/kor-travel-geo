# T-165 주소 정규화/파싱 견고성 강화

## 목표

T-165는 기존 `core.normalize.parse_address()`가 exact lookup에 필요한 핵심 키를 잃지 않도록 입력 변형을 보수적으로 흡수한다. 대상은 시도 약어·구/신 표기, 불규칙 공백, 괄호 노트, 전각 숫자·대시, 도로명과 건물번호 사이 무공백, `번`/`번지` 접미, 영문 혼용 prefix, 도로명 오타 입력의 fuzzy fallback 번호 보존이다.

이번 작업은 public DTO와 OpenAPI schema를 바꾸지 않는다. 입력 문자열을 더 잘 canonicalize할 뿐, 새 응답 필드나 외부 provider 호출 경로는 추가하지 않는다.

## 구현

- `normalize_spaces()`가 `NFKC` 정규화로 전각 숫자를 ASCII 숫자로 접고, 여러 Unicode dash를 `-`로 통일한다.
- 쉼표류 구분자는 공백으로 바꾸고, `189 - 4`처럼 숫자 사이에 공백이 낀 하이픈은 `189-4`로 접는다.
- 괄호 노트는 기존 `()`에 더해 NFKC 이후의 대괄호/중괄호 형태도 같은 방식으로 분리한다.
- 시도 별칭에 `서울시`, `부산시`, `대구시`, `인천시`, `대전시`, `울산시`, `세종시`, `강원도`, `전라북도`, `전북도`, `제주도`, `충북도`, `충남도`, `전남도`, `경북도`, `경남도`를 추가했다.
- 도로명 parser는 `성복1로35`, `왕산로189-4`처럼 도로명과 건물번호 사이 공백이 없는 입력도 허용한다.
- 지번 parser는 `산12 - 3번지`처럼 산 지번, 본번-부번 주변 공백, `번`/`번지` 접미를 exact lookup 키로 보존한다.

## 테스트와 corpus

- `tests/unit/test_t165_normalization.py`가 정규화 helper, 도로명 변형, 지번 변형, core geocode repository 전달 값을 고정한다.
- `T140-GEO-WHITESPACE-ALIAS-001`은 `서울시 동대문구 왕산로１８９－４ (청량리동)` 입력을 기본 live normalization acceptance case로 좁혔다.
- Fixture smoke 결과는 25/25 통과했고 corpus SHA-256은 `0b4ff00d1a59520da3237daf57c51e9be1e870a699976f1b86e1d48482d32b99`이다.

## 한계

영문 주소를 한국어 주소로 transliteration하지 않는다. 예를 들어 `Wangsan-ro 189-4`만 주어진 입력은 `왕산로`로 바꾸지 않는다. 이번 범위의 영문 혼용은 `Seoul ... Wangsan-ro 왕산로 189-4`처럼 한국어 도로명이 함께 들어오는 경우 앞쪽 영문 토큰 때문에 도로명/번호 추출이 깨지지 않는다는 의미다.

도로명 오타 자체의 후보 ranking은 T-171 fuzzy fallback이 담당한다. T-165는 오타 입력에서도 본번·부번·지하구분을 잃지 않아 fuzzy lookup이 같은 건물번호 계약을 유지하게 하는 범위에 머문다.

## 다음 작업

Agent A 다음 순서는 `T-143` geocode/search query plan 안정화다. T-165가 넓힌 parser 변형은 T-143에서 exact preflight와 fuzzy fallback plan을 측정할 때 입력 분포에 포함한다.
