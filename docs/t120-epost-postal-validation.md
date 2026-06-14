# T-120 epost 우편번호 수동 적재·검증

## 범위

T-120은 디스크에 없는 우편번호 보조 원천인 epost `15000302` 자료를 수동으로 받아 `postal_pobox`, `postal_bulk_delivery`에 적재하기 전 검증하는 경로를 정리한다. 핵심 rebuild, `source_match_set`, `mv_geocode_target` swap과는 독립이며, phase ② T-207의 server-fetch/RustFS register 흐름이 같은 검증 모듈을 재사용할 수 있어야 한다.

이번 작업의 구현 표면은 다음과 같다.

- `src/kortravelgeo/loaders/epost_validation.py`: 사서함·다량배달처 공통 검증 모듈.
- `ktgctl load pobox <path>` / `ktgctl load bulk <path>`: 적재 전 검증 요약 출력 후 COPY.
- `ktgctl load epost --source <zip-or-dir>`: ZIP 압축 해제, 사서함·다량배달처 파일 발견, 각 파일 검증 요약 출력 후 COPY.
- `download_epost_zip()`: 공공데이터포털 응답이 직접 ZIP이거나 `fileLocplc` XML인 경우를 모두 처리.
- API job `pobox_load` / `bulk_load`: 기존 로더 함수 진입점에서 같은 검증을 수행한다.

## 검증 규칙

검증은 파일 전체를 DB에 넣기 전에 실패 가능한 항목을 먼저 드러내는 sanity gate다.

| 항목 | 규칙 |
|------|------|
| 인코딩 | `utf-8-sig` 우선, 실패 시 `cp949` |
| 행수 | 데이터 행 0건이면 실패 |
| 필수 컬럼·값 | 사서함은 `zip_no`/`우편번호`, 다량배달처는 `zip_no`/`우편번호`와 `bulk_name`/`다량배달처명`/`기관명` |
| 우편번호 형식 | 정확히 5자리 숫자 |
| 사서함 종류 | 값이 있으면 `PO` 또는 `PG`만 허용. 없으면 기존 로더와 같이 `PO` 기본값 |
| 사서함 번호 | `pobox_no_mn`/`사서함본번`, `pobox_no_sl`/`사서함부번` 값이 있으면 unsigned integer |
| 중복 | 사서함은 COPY PK가 되는 `bd_mgt_sn`/`건물관리번호` 기준, 없으면 `pobox:<row>` fallback 기준. 다량배달처는 `zip_no + bulk_name + bd_mgt_sn + detail` exact key 기준 |

검증 결과는 `PostalValidationSummary`로 반환한다. CLI에서는 다음 요약을 출력한다.

```text
epost pobox validation: passed
  path: ...
  rows: total=1, valid=1, encoding=cp949
  checks: missing_required=0, invalid_zip=0, invalid_kind=0, invalid_integer=0, duplicates=0
```

실패 시 `LoaderError`가 발생하며, COPY는 실행하지 않는다.

## 수동 실행

이미 받은 ZIP 또는 압축 해제 디렉터리가 있으면 다음처럼 실행한다.

```bash
ktgctl load epost --source data/epost/epost_downloadKnd_1_YYYYMMDDHHMMSS.zip
```

개별 파일만 적재할 수도 있다.

```bash
ktgctl load pobox data/epost/사서함.txt
ktgctl load bulk data/epost/다량배달처.txt
```

`--source`가 없으면 `KTG_EPOST_API_KEY`와 `KTG_EPOST_DOWNLOAD_URL` 설정을 사용해 수동 다운로드한다. 이 경로는 직접 ZIP 응답과 `fileLocplc` XML 응답을 모두 지원한다. 자동·스케줄 다운로드는 여전히 범위 밖이다.

## T-207 재사용 경계

T-207은 "epost 받기" 버튼에서 server-fetch → RustFS register → `pobox_load`/`bulk_load` → 검증 report로 이어진다. 이때 T-120 모듈을 다음처럼 재사용하면 된다.

- fetch 결과 파일의 encoding/row/header/format/duplicate 검증: `validate_pobox_file()`, `validate_bulk_file()`.
- 실패 report 저장 전 사람이 읽을 수 있는 요약: `format_postal_validation_summary()`.
- DB 반영 전 hard gate: `ensure_postal_validation_passed()`.

ZIP 구조 불일치와 기준월 mismatch는 T-207의 fetch/session state에서 다루고, 파일 내부 sanity는 이 모듈이 담당한다.

## 검증

이번 PR은 실제 epost 원천 파일이 로컬 `data/`에 없어서 synthetic fixture로 고정했다.

- `tests/unit/test_epost_validation.py`: 한글/영문 alias, `utf-8-sig`/`cp949`, 형식 오류, 중복 오류.
- `tests/unit/test_epost_downloader.py`: 직접 ZIP 응답과 `fileLocplc` XML 응답.
- `tests/unit/test_cli_contract.py`: CLI가 공유 검증 helper를 우회하지 않는 계약.
