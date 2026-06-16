# T-127 optional source 구조 validator 강화

작성일: 2026-06-16
담당: Codex(Agent A)

## 배경

T-216 live acceptance에서 C11~C17 optional source 8개 category/40개 archive는 모두 source registry에 등록되고 run-validation도 `runnable=7`, `skipped=0`, `failed=0`으로 통과했다. 다만 optional single-file category 일부는 상세 구조 profile이 없어 `warning`으로만 통과했다.

T-127은 이 warning의 의미를 좁히기 위해 single-file optional 원천의 archive member naming, 필수 파일, SHP sidecar, 기준월 sanity를 category별로 검증한다.

## 반영 범위

대상 category는 다음 6개다.

| category | 검증 |
|----------|------|
| `detail_address_db_full` | `adrdc_*.txt` 17개 |
| `national_point_grid_shape` | `TL_SPPN_GRID_100KM/10KM/1KM/100M` SHP layer 4개와 `.shp/.shx/.dbf` sidecar |
| `national_point_grid_center` | `SPPN_*.TXT` 1개 |
| `civil_service_institution_map` | `민원행정기관*` SHP layer 1개와 `.shp/.shx/.dbf` sidecar |
| `address_db_full` | `주소_*.txt`, `부가정보_*.txt`, `지번_*.txt` 각 17개와 `개선_도로명코드_*.txt` 1개 |
| `building_db_full` | `build_*.txt`, `jibun_*.txt` 각 17개와 `road_code_total*.txt` 1개 |

SHP `.prj` 누락은 기존 정책대로 실패가 아니라 `warning`이다. 국가지점번호 도형 실제 원천은 `.prj`가 없으므로 T-216의 수용 결과를 깨지 않고 `warning`으로 남는다. 필수 layer, TXT prefix, 필수 sidecar가 없으면 `failed`다.

## 구현 메모

- `core.source_validation.VALIDATOR_VERSION`을 `t127.1`로 올렸다.
- 기존 GDAL-free 구조 validator에 T-127 profile을 추가했다.
- legacy ZIP의 CP949 member name을 UTF-8 flag가 없을 때 복원한다. 주소DB와 민원행정기관 전자지도처럼 한글 파일명을 가진 ZIP도 prefix/layer 검증을 받을 수 있다.
- `ManifestMember.detected_yyyymm`을 scanner가 채우고, 한 archive 안에 여러 기준월이 섞이면 `warning`으로 보고한다.
- `national_point_grid_center`의 catalog `expected_member_kinds`는 실제 원천에 맞춰 `grid_center_txt`로 정정했다.

## 실제 원천 smoke

`tests/integration/test_optional_real_t127_source_validation.py`는 `data/juso/unused` 또는 `F:/dev/geodata/juso/unused`가 있을 때만 ZIP 중앙 디렉터리를 읽어 smoke를 수행한다. 대용량 TXT/SHP payload는 열지 않는다.

현재 보존 원천 기준 결과:

| category | 실제 archive | 결과 |
|----------|--------------|------|
| `detail_address_db_full` | `202604_상세주소DB_전체분.zip` | `passed` |
| `national_point_grid_shape` | `국가지점번호도형_5월분.zip` | `warning` (`.prj` 없음) |
| `national_point_grid_center` | `국가지점번호중심점_5월분.zip` | `passed` |
| `civil_service_institution_map` | `민원행정기관전자지도_240124.zip` | `passed` |
| `address_db_full` | `202605_주소DB_전체분.zip` | `passed` |
| `building_db_full` | `202605_건물DB_전체분.zip` | `passed` |

## 검증

Windows focused 검증:

```bash
$env:PYTHONPATH='F:\dev\kor-travel-geo-codex\src'
python -m pytest tests/unit/test_t203b_register_recompute.py tests/unit/test_t203b_member_scan.py tests/unit/test_t201_category_catalog.py tests/integration/test_optional_real_t127_source_validation.py -q
python -m ruff check src/kortravelgeo/core/source_validation.py src/kortravelgeo/infra/source_member_scan.py src/kortravelgeo/core/source_categories.py tests/unit/test_t203b_register_recompute.py tests/unit/test_t203b_member_scan.py tests/integration/test_optional_real_t127_source_validation.py
```

결과는 focused pytest `61 passed`, Ruff 통과다.

WSL ext4 테스트 미러 전체 검증:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src/kortravelgeo
lint-imports
python scripts/export_openapi.py --check
```

결과는 pytest `990 passed, 61 skipped`, Ruff 통과, mypy `145 source files` 통과, import-linter `Layered architecture KEPT`, OpenAPI drift 없음이다.
