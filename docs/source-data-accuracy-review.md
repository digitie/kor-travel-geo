# 미사용 원천 데이터 정확도 개선 검토

> 최신 최종 판정은 `docs/optional-source-usage-decision.md`를 우선한다. 이 문서는 `unused` 원천의 가능성을 검토한 배경 자료이며, PR #193/#194의 clean-slate 분석과 T-125 C11 serving preflight 이후 `도로명주소 건물 도형` 출입구 blanket 승격은 no-go로 갱신됐다. 국가지점번호 좌표는 활용하되, `국가지점번호 도형/중심점` 파일은 10m 좌표 원천이 아니라 검증·overlay 원천으로만 본다.

이 문서는 `F:\dev\geodata\juso\unused`에 보존한, 기본 full-load가 직접 쓰지 않거나 선택/조건부로만 쓰는 원천을 검토한다. 목적은 새 원천을 무작정 serving table에 섞는 것이 아니라, **정확도 개선에 직접 쓸 수 있는지**, **검증/품질관리에는 쓸 수 있는지**, **별도 loader나 테이블 계약이 필요한지**를 다른 에이전트가 바로 판단할 수 있게 남기는 것이다.

## 결론 요약

| 원천 | 직접 정확도 개선 | 검증용 가치 | 권장 판단 |
|------|------------------|-------------|-----------|
| `도로명주소 출입구 정보` | 높음 | 높음 | `juso`와 기준월을 맞추면 대표 좌표 1순위 후보로 계속 활용 |
| `국가지점번호 도형` | 낮음 | 중간 | 10m 좌표 정확도 개선용은 아님. grid parser/formatter 검증과 지도 overlay에 적합 |
| `국가지점번호 중심점` | 낮음 | 높음 | 100m 이하 prefix 좌표 검증, reverse 국가지점번호 formatter 검증에 적합 |
| `도로명주소 건물 도형` | 현행 대표 좌표 승격은 낮음(T-125 no-go) | 높음 | `TL_SPBD_ENTRC` blanket 승격 금지. `TL_SGCO_RNADR_MST`/`TL_SPOT_CNTC`는 geometry·검증용 |
| `건물군 내 상세주소 동 도형` | 상세주소 기능에는 높음, 일반 주소에는 낮음 | 높음 | 상세주소 동/출입구 별도 기능 후보. 기본 geocode 대표 좌표에는 섞지 않음 |
| `상세주소DB` | 상세주소 기능에는 중간 | 높음 | 상세주소 parser/열거 원천. 좌표가 없으므로 기본 주소 geocode 개선용 아님 |
| `주소DB` | 낮음 | 중간 | 현 도로명주소 한글 정본과 중복 성격. 스냅샷/행 수/키 검증용 |
| `건물DB` | 낮음~중간 | 높음 | 좌표 원천은 아니지만 건물 속성/키/기준월 검증에 유용 |
| `민원행정기관전자지도` | 주소 geocode에는 낮음, POI에는 중간 | 중간 | 행정기관 POI 검색/검증 후보. 주소 정본에는 섞지 않음 |
| 과거 snapshot | 낮음 | 중간 | 회귀/일변동 검증용. 최신 serving 원천으로 쓰지 않음 |

즉, 일반 도로명주소 geocode/reverse 정확도에 바로 도움이 되는 안정 후보는 현행 `위치정보요약DB`와 same-month `도로명주소 출입구 정보`다. `도로명주소 건물 도형`의 출입구 계열은 유력 후보였지만 T-125에서 대표 좌표 blanket 승격이 no-go로 판정됐으므로 검증·outlier 분석 대상으로 남긴다. 국가지점번호는 좌표를 활용하지만, 도형/중심점 파일은 현재 10m 계산식보다 정밀한 좌표를 주는 데이터가 아니므로 검증과 coarser grid 지원에 적합하다.

## 현재 구현 기준

현재 국가지점번호 구현은 다음 경로다.

- `src/kortravelgeo/core/sppn.py`
  - `parse_national_point_number()`는 한글 2자 + x 4자리 + y 4자리 형식을 EPSG:5179 **10m cell 중심**으로 계산한다.
  - `format_national_point_number_from_5179()`는 EPSG:5179 point를 포함하는 10m cell 문자열로 만든다.
- `src/kortravelgeo/core/geocoder.py`
  - 일반 주소 파싱 전에 국가지점번호 문자열을 먼저 감지한다.
  - 좌표를 계산한 뒤 `GeocodeRepository.lookup_sppn_area()`로 `tl_sppn_makarea` 포함 여부를 확인한다.
- `src/kortravelgeo/infra/geocode_repo.py`
  - `tl_sppn_makarea`에 `ST_Covers(m.geom, p.geom)`로 포함 여부를 조회한다.
- `src/kortravelgeo/core/reverse_geocoder.py`
  - reverse는 일반 주소 후보와 별개로 `repo.sppn_areas()`를 호출해 `x_extension.sppn_makarea`를 붙인다.
- `src/kortravelgeo/infra/reverse_repo.py`
  - `tl_sppn_makarea` 포함 polygon을 면적 오름차순으로 조회한다.

현재 기본 full-load 필수 원천은 `juso`, `parcel_link`, `locsum`, `navi`, `shp`다. `roadaddr_entrance`, `sppn_makarea`는 선택 원천이다. 이 문서의 검토 대상 대부분은 선택 원천이거나 아직 loader가 없는 미사용 원천이다.

## 검토 기준

| 판정 | 의미 |
|------|------|
| 직접 활용 | serving 결과의 좌표, 후보 순위, 후보 coverage를 개선할 수 있음 |
| 조건부 활용 | 기준월 일치, 입력 형식, 별도 feature flag, 낮은 confidence 등 조건이 필요함 |
| 검증용 활용 | serving에는 넣지 않아도 품질 게이트, regression, source consistency 확인에 쓸 수 있음 |
| 보류 | 의미가 다르거나 중복/오염 위험이 커서 별도 테이블과 비교 작업 전에는 쓰지 않음 |

원칙은 다음과 같다.

- 기존 `mv_geocode_target`에 새 원천을 바로 union하지 않는다.
- 새 원천은 먼저 별도 staging/analysis table에 적재한다.
- `source_yyyymm`, `source_file`, `source_archive`, 내부 member, checksum을 남긴다.
- 기준월이 다른 원천을 좌표 후보로 승격할 때는 명시적인 confirmation과 consistency report가 필요하다.
- vworld 호환 응답 필드는 깨지지 않게 하고 자체 정보는 `x_extension` 또는 v2 `metadata`에 둔다.

## 국가지점번호 도형

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\국가지점번호 도형\202405\국가지점번호도형_5월분.zip
```

ZIP member:

| layer | geometry | DBF records | DBF fields |
|-------|----------|------------:|------------|
| `TL_SPPN_GRID_100KM` | Polygon | 30 | `SPO_100KM` |
| `TL_SPPN_GRID_10KM` | Polygon | 1,341 | `SPO_10KM` |
| `TL_SPPN_GRID_1KM` | Polygon | 106,596 | `SPO_1KM` |
| `TL_SPPN_GRID_100M` | Polygon | 10,076,774 | `SPO_100M` |

### 정확도 개선 가능성

직접 정확도 개선 가능성은 낮다. 이유는 현재 parser가 이미 10m cell 중심 좌표를 수식으로 계산하기 때문이다. 이 도형 원천은 최대 100m 격자 polygon까지만 제공한다. 따라서 `다바 7363 4856` 같은 10m 정밀 입력에 대해 100m polygon을 조회하면 오히려 더 거친 위치가 된다.

다만 다음 기능에는 가치가 있다.

- 100km/10km/1km/100m prefix 입력을 별도 기능으로 허용할 때 bbox/centroid를 제공한다.
- 디버그 UI에서 국가지점번호 grid overlay를 표시한다.
- parser/formatter의 격자 원점, grid letter, 좌표계 변환을 샘플 검증한다.
- `tl_sppn_makarea`와 grid가 맞물리는지, 표기 의무지역 내부에 grid가 얼마나 분포하는지 품질 분석한다.

### 검증용 가치

검증용 가치는 중간이다. 특히 `TL_SPPN_GRID_100M`은 1천만 polygon이라 DB에 상시 적재하면 공간과 load 시간이 크다. 기본 DB에는 넣지 말고, 다음 방식이 낫다.

- ZIP/DBF streaming으로 sample 기반 parser 검증
- 필요 시 별도 임시 DB 또는 parquet/flat index에서 100m code coverage 확인
- UI overlay는 100km/10km/1km까지만 우선 사용하고, 100m는 bbox zoom threshold를 둔다.

### 권장

기본 geocode 정확도 개선 원천으로 쓰지 않는다. 후속 작업을 한다면 `tl_sppn_grid_100km`, `tl_sppn_grid_10km`, `tl_sppn_grid_1km`, `tl_sppn_grid_100m` 같은 별도 table을 만들되, `TL_SPPN_GRID_100M`은 상시 serving보다 검증/overlay 전용으로 먼저 둔다.

## 국가지점번호 중심점

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\국가지점번호 중심점\202405\국가지점번호중심점_5월분.zip
```

ZIP member:

```text
SPPN_20240508.TXT
```

전체 행 수는 10,184,741행이다. 첫 필드 길이별 분포는 다음과 같다.

| 첫 필드 길이 | 격자 수준 | 행 수 | 예시 |
|-------------:|-----------|------:|------|
| 2 | 100km | 30 | `가다|750000.0|1550000.0` |
| 4 | 10km | 1,341 | `나바45|845000.0|1855000.0` |
| 6 | 1km | 106,596 | `나나8477|884500.0|1477500.0` |
| 8 | 100m | 10,076,774 | `나나754788|875450.0|1478850.0` |

좌표는 EPSG:5179 계열 meter 좌표로 해석된다. 예를 들어 `나나754788`은 100m cell 중심 좌표 `875450, 1478850`과 맞는다.

### 정확도 개선 가능성

직접 정확도 개선 가능성은 낮다. 현재 parser가 지원하는 10m 정밀 국가지점번호는 한글 2자 + x 4자리 + y 4자리다. 중심점 파일은 100m까지의 prefix 중심점만 제공하므로, 10m 입력 좌표를 더 정확하게 만들 수 없다.

하지만 다음 개선은 가능하다.

- 현재 parser가 거부하는 100km/10km/1km/100m prefix 입력을 별도 `precision`으로 받을 수 있다.
- reverse에서 10m 국가지점번호와 함께 100m/1km parent grid metadata를 제공할 수 있다.
- formatter가 만든 100m prefix 중심점이 원천 파일과 일치하는지 regression 테스트를 만들 수 있다.
- `TL_SPPN_GRID_100M` polygon 중심과 TXT 중심점 일치 여부를 검증할 수 있다.

### 검증용 가치

높다. DB에 1천만 중심점을 상시 넣지 않아도, streaming 검증으로 다음을 확인할 수 있다.

- `GRID_LETTERS`, 원점, cell size 계산식이 원천과 일치하는지
- 100m prefix와 EPSG:5179 center 좌표가 일치하는지
- 좌표계 전환 뒤 한국 영역 밖 후보가 없는지
- `format_national_point_number_from_5179()` 결과의 parent 100m prefix가 원천에 존재하는지

### 권장

직접 serving table이 아니라 `tests/fixtures` 또는 선택형 integration validation으로 먼저 쓴다. 기능화한다면 `NationalPointNumber.precision_m`을 도입하고, 현재 10m parser와 100m 이하 prefix parser를 명확히 분리한다.

## 도로명주소 건물 도형

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\도로명주소 건물 도형\202604\<시도>.zip
```

전국 합산 DBF record:

| layer | geometry | records | 주요 필드 |
|-------|----------|--------:|-----------|
| `TL_SGCO_RNADR_MST` | Polygon | 6,406,445 | `ADR_MNG_NO`, `SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `BUL_MAN_NO`, `EQB_MAN_SN`, `EFFECT_DE` |
| `TL_SPBD_ENTRC` | Point | 6,454,571 | `BUL_MAN_NO`, `ENTRC_SE`, `ENT_MAN_NO`, `EQB_MAN_SN`, `OPERT_DE`, `SIG_CD` |
| `TL_SPOT_CNTC` | PolyLine | 6,402,036 | `BSI_INT_SN`, `CNT_DRC_LN`, `CNT_DST_LN`, `ENT_MAN_NO`, `OPERT_DE`, `RDS_MAN_NO`, `RDS_SIG_CD`, `SIG_CD` |

문서 이력 T-040에서는 이 bundle이 전자지도 `TL_SPBD_BULD`의 단순 중복이 아니라고 결론냈다. 세종/경남 비교에서 `TL_SGCO_RNADR_MST`와 전자지도 `TL_SPBD_BULD`의 natural key 교집합이 낮았고, address polygon과 building polygon의 의미가 다르다고 봤다.

### 정확도 개선 가능성

직접 정확도 개선 가능성은 중간이다. 특히 point/line 계열은 가치가 있다.

- `TL_SPBD_ENTRC`는 건물 출입구 point로, `tl_locsum_entrc`, `tl_roadaddr_entrc`, 전자지도 `TL_SPBD_ENTRC`와 비교해 대표 좌표 품질을 높일 수 있다.
- `TL_SPOT_CNTC`는 출입구와 도로 구간 연결선으로 보이며, C8 같은 도로명-출입구 인접성 검증을 더 설명력 있게 만들 수 있다.
- `TL_SGCO_RNADR_MST`는 주소 단위 polygon일 가능성이 있어, 건물 polygon 중심보다 주소 polygon 기반 centroid가 더 적절한 일부 케이스를 찾을 수 있다.

하지만 바로 `tl_spbd_buld_polygon`을 대체하면 안 된다.

- 전자지도 `TL_SPBD_BULD`는 건물 polygon 정본 역할이고, `TL_SGCO_RNADR_MST`는 주소 단위 polygon으로 의미가 다르다.
- 동일 key로 완전 중복되지 않는다.
- 기존 C1/C2/C4/C5 정합성 의미가 바뀐다.

### 검증용 가치

높다. 별도 분석 table을 만들면 다음 검증이 가능하다.

- `tl_locsum_entrc` vs `TL_SPBD_ENTRC` 거리 분포
- `tl_roadaddr_entrc` vs `TL_SPBD_ENTRC` 기준월 일치 시 거리 분포
- `mv_geocode_target.pt_5179`가 address polygon 내부에 있는지
- `TL_SPOT_CNTC`가 `TL_SPRD_MANAGE`/`TL_SPRD_INTRVL`과 일관되는지
- 출입구 후보가 여러 개인 건물에서 대표 좌표 선택 기준 개선

### 권장

별도 테이블 후보:

- `tl_roadaddr_buld_polygon`
- `tl_roadaddr_buld_entrc`
- `tl_roadaddr_spot_cntc`

도입 순서는 다음이 안전하다.

1. loader 없이 ZIP streaming 비교 스크립트로 `tl_locsum_entrc`, `tl_roadaddr_entrc`, 전자지도 `TL_SPBD_ENTRC`와 거리/키 overlap 재측정
2. 별도 table에 적재하고 C2/C4/C8 validation report 보강
3. 대표 좌표 승격은 feature flag와 confidence rule을 둔 뒤 제한적으로 적용

## 건물군 내 상세주소 동 도형

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\건물군 내 상세주소 동 도형\202604\<시도>.zip
```

전국 합산 DBF record:

| layer | geometry | records | 주요 필드 |
|-------|----------|--------:|-----------|
| `TL_SGCO_RNADR_DONG` | Polygon | 6,454,292 | `ADR_MNG_NO`, `BD_MGT_SN`, `SIG_CD`, `BUL_MAN_NO`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `EQB_MAN_SN` |
| `TL_SPBD_ENTRC_DONG` | Point | 424,639 | `SIG_CD`, `ENT_MAN_NO`, `BUL_MAN_NO`, `ENTRC_SE`, `OPERT_DE`, `ENTRC_DC` |

T-041 문서 이력에서는 세종/경남 기준 `TL_SGCO_RNADR_DONG`이 전자지도 `TL_SPBD_BULD`의 부분집합이라고 판단했다.

### 정확도 개선 가능성

일반 도로명주소 geocode 정확도 개선 가능성은 낮다. 이 원천은 기본 건물/주소 좌표를 대체하기보다, 상세주소 동 단위의 더 세밀한 표시를 위한 데이터다.

상세주소 기능에는 가치가 높다.

- `동`, `호` 같은 상세주소를 입력받는 별도 geocode를 만들 때 동 polygon/동 출입구 point를 활용할 수 있다.
- 같은 건물 안에서 상세주소 동별 진입 위치나 polygon을 구분하는 UI/관리 기능을 만들 수 있다.
- 상세주소DB와 결합하면 상세주소 문자열 parser 검증에 쓸 수 있다.

### 검증용 가치

높다.

- 상세주소DB `adrdc_*.txt`와 `TL_SGCO_RNADR_DONG.BD_MGT_SN`/`ADR_MNG_NO` 일치성 검증
- 전자지도 `TL_SPBD_BULD`와의 containment/overlap 검증
- `TL_SPBD_ENTRC_DONG`이 현 출입구 후보와 얼마나 떨어지는지 검증
- 상세주소가 없는 일반 주소 결과에 상세주소 동 정보를 잘못 붙이지 않는 regression 테스트

### 권장

기본 serving path에는 넣지 않는다. 후속 기능이 필요하면 별도 도메인으로 둔다.

- `tl_detail_dong_polygon`
- `tl_detail_dong_entrc`
- `detail_address_geocode` 또는 v2 `match_kind="detail"` 후보

## 상세주소DB

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\202605_상세주소DB_전체분.zip
```

확인값:

- `adrdc_*.txt` 17개
- 전국 3,204,565행
- 서울 샘플 첫 행 기준 16컬럼

예시:

```text
11110|5877|19170|93499|0||1|||0|1111011300100830000028931|1111011300|111102100002|0|13|3
```

### 정확도 개선 가능성

일반 주소 geocode에는 직접 도움이 적다. 상세주소DB는 기본 도로명주소/지번 정본을 보강하는 상세주소 단위 데이터다. 주소 후보 좌표 자체를 더 정확하게 만들기보다는 상세주소 입력을 받았을 때 건물 내부 단위를 식별하는 데 쓰는 것이 맞다.

### 검증용 가치

높다.

- `건물군 내 상세주소 동 도형`과 상세주소 행의 key 검증
- 상세주소 입력 parser의 테스트 corpus 생성
- 상세주소가 기본 주소 후보와 잘못 병합되는지 방지하는 negative test

### 권장

현 기본 geocode에는 넣지 않는다. 상세주소 feature를 만들 때 별도 parser/loader와 함께 사용한다.

## 주소DB

### 원본 구조

최신 경로:

```text
F:\dev\geodata\juso\unused\202605_주소DB_전체분.zip
```

전국 행 수:

| member 패턴 | 행 수 | 비고 |
|-------------|------:|------|
| `주소_*.txt` | 6,420,025 | 도로명 주소 계열 |
| `부가정보_*.txt` | 6,420,025 | 부가 속성 |
| `지번_*.txt` | 8,191,051 | 지번 계열 |
| `개선_도로명코드_전체분.txt` | 370,024 | 도로명 코드 |

서울 샘플:

```text
주소_서울특별시.txt: 1111011900102150000000001|111102005001|01|0|145|2|03186||||0
부가정보_서울특별시.txt: 1111010100100010000030843|1111051500|청운효자동|03046|||청운벽산빌리지|청운벽산빌리지|1
지번_서울특별시.txt: 1111010100100010000030843|1|1111010100|서울특별시|종로구|청운동||0|1|0|1
개선_도로명코드_전체분.txt: 111102005001|세종대로|Sejong-daero|00|서울특별시|Seoul|종로구|Jongno-gu|||2||0||||
```

### 정확도 개선 가능성

직접 정확도 개선 가능성은 낮다. 현재 full-load의 텍스트 정본은 `도로명주소 한글_전체분.zip`이며, `주소DB`는 과거 문서에서 "구 매칭데이터" 성격으로 언급된다. 같은 주소 체계를 다른 layout으로 제공하는 중복 원천에 가깝다.

다만 다음 경우에는 유용하다.

- `도로명주소 한글_전체분`과 행 수/키 차이 검증
- 도로명 코드 영문명/이동 사유 같은 보조 속성 보강 검토
- `지번_*.txt`를 `tl_juso_parcel_link`와 비교해 누락 지번 후보 검출

### 검증용 가치

중간이다. 별도 loader 없이 ZIP streaming 비교로 충분하다. serving에 넣으려면 `bd_mgt_sn`, 도로명 코드, 지번 key가 현재 DTO/응답 계약과 어떻게 대응되는지 먼저 명세화해야 한다.

### 권장

기본 serving에는 넣지 않는다. `source_set` manifest와 C10 기준월 검증, row-count drift 검증용으로 먼저 사용한다.

## 건물DB

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\202605_건물DB_전체분.zip
```

전국 행 수:

| member 패턴 | 행 수 | 비고 |
|-------------|------:|------|
| `build_*.txt` | 10,722,592 | 건물 단위 속성 |
| `jibun_*.txt` | 1,771,035 | 건물-지번 보조 |
| `road_code_total.txt` | 370,024 | 도로명 코드 |

서울 샘플:

```text
build_seoul.txt: 1111010100|서울특별시|종로구|청운동||0|144|3|111103100012|자하문로|0|94|0|||1111010100101440003031291|01|1111051500|청운효자동|03047|||||||0|03047|0||
jibun_seoul.txt: 1111012000|서울특별시|종로구|신문로1가||0|150|0|111102005001|0|149|0|1114|
road_code_total.txt: 11110|2005001|세종대로|Sejong-daero|00|서울특별시|종로구|2|||||0|||Seoul|Jongno-gu||20100520|
```

### 정확도 개선 가능성

직접 좌표 정확도 개선 가능성은 낮다. 좌표 원천이 아니라 건물/도로명/지번 속성 원천이다. 다만 최신 `202605` snapshot이고, `build_*.txt` 행 수가 전자지도 `TL_SPBD_BULD`와 유사한 1천만 단위이므로 다음 보강 후보가 된다.

- `tl_juso_text`가 6.4M 주소 행인 반면 `build_*.txt`는 10.7M 건물 단위라, 주소가 없는 부속 건물/건물군 속성 검증에 쓸 수 있다.
- `tl_spbd_buld_polygon`과 `BD_MGT_SN`/natural key 대응 검증에 쓸 수 있다.
- 우편번호, 행정동, 건물 용도 같은 속성 차이를 점검할 수 있다.

### 검증용 가치

높다.

- `tl_juso_text`, `tl_spbd_buld_polygon`, `tl_navi_buld_centroid`의 기준월 차이 검증
- building key 누락/중복 검증
- 주소 없는 건물 polygon 또는 centroid 후보의 원인 분석
- `road_code_total.txt`와 기존 도로명 코드 정합성 확인

### 권장

좌표 후보로 직접 쓰지 않는다. 별도 `stg_building_db_*` 또는 일회성 consistency job으로 먼저 활용한다. 정확도 개선으로 이어지려면 "건물DB 속성으로 어떤 좌표 후보를 바꿀 것인가"가 별도 ADR로 정의되어야 한다.

## 도로명주소 전자지도 내부 미사용 layer

기본 `shp` 원천은 사용하지만, 내부 모든 layer를 적재하지는 않는다.

현재 미사용 layer:

- `TL_SPBD_EQB`
- `TL_SPBD_ENTRC`

`TL_SPBD_ENTRC`는 point 6,405,672행으로, 전자지도 건물 출입구 point다. 기본 serving은 현재 `tl_locsum_entrc`와 선택 `tl_roadaddr_entrc`, `tl_navi_buld_centroid`를 중심으로 좌표를 정한다.

### 정확도 개선 가능성

`TL_SPBD_ENTRC`는 중간 이상이다. 다만 `도로명주소 건물 도형`의 `TL_SPBD_ENTRC`, `도로명주소 출입구 정보`, `tl_locsum_entrc`와 역할이 겹치므로, 한꺼번에 섞으면 source priority가 불분명해진다.

`TL_SPBD_EQB`는 건물군/동 관련 polygon 성격이라 기본 주소 좌표 개선보다는 상세주소/건물군 분석에 가깝다.

### 검증용 가치

높다.

- `tl_locsum_entrc`와 전자지도 출입구 거리 비교
- `도로명주소 건물 도형` 출입구와 중복/차이 비교
- direct 출입구 `RNENTDATA_*`가 없는 기준월에서 fallback 후보 검토

### 권장

바로 기본 좌표 후보로 넣지 않는다. 출입구 후보 source priority를 재설계할 때 `tl_electronic_buld_entrc` 같은 별도 table로 먼저 도입한다.

## 내비게이션용DB 내부 미사용 member

`202604_내비게이션용DB_전체분.7z`에는 다음이 있다.

- `match_build_*.txt` 17개: 현재 사용
- `match_rs_entrc.txt` 1개: 현재 사용
- `match_jibun_*.txt` 17개: 현재 미사용

`match_jibun_*.txt`는 지번 매칭 보조로 보이며, 현재 `tl_juso_parcel_link`나 reverse parcel 품질 검증에 쓸 수 있다.

### 정확도 개선 가능성

직접 좌표 개선 가능성은 낮다. 다만 parcel reverse와 지번 후보 coverage 검증에는 가치가 있다.

### 검증용 가치

중간이다.

- `tl_juso_parcel_link`와 PNU/link coverage 비교
- 지번 reverse 후보가 약한 지역의 누락 원인 분석
- 내비 centroid와 지번 link가 맞는지 cross-check

### 권장

별도 loader를 바로 만들기보다 `tl_juso_parcel_link` 품질 검증 script의 비교 원천으로 먼저 사용한다.

## 민원행정기관전자지도

### 원본 구조

경로:

```text
F:\dev\geodata\juso\unused\민원행정기관전자지도_240124.zip
```

구성:

- `민원행정기관_202401.shp`
- `민원행정기관_202401.shx`
- `민원행정기관_202401.dbf`
- `민원행정기관_202401.prj`

DBF record count는 26,142행이다. 필드는 다음과 같다.

| field | 의미 추정 |
|-------|-----------|
| `유형` | 기관 유형 |
| `상세분류` | 상세 분류 |
| `시군구코드` | 시군구 코드 |
| `도로명코드` | 도로명 코드 |
| `도로명주소` | 도로명주소 문자열 |
| `기관명` | 기관명 |
| `위치X`, `위치Y` | EPSG:5179 계열 좌표 |
| `전화번호` | 전화번호 |

PRJ는 `Korea_2000_Unified_CS`로, 현재 내부 좌표계 EPSG:5179와 같은 계열로 볼 수 있다.

### 정확도 개선 가능성

일반 주소 geocode 정확도 개선에는 낮다. 이 원천은 주소 정본이 아니라 행정기관 POI다.

POI/기관 검색에는 중간 가치가 있다.

- `keyword=주민센터`, `기관명` 검색 같은 별도 POI match_kind 후보
- 행정기관 주소의 좌표 검증
- 주소 geocode 결과가 기관 좌표와 크게 다른 경우 data-quality sample 생성

### 검증용 가치

중간이다. 기관 주소 문자열을 기존 geocoder로 돌린 결과와 `위치X/Y`를 비교하면 도로명주소/기관 POI 품질을 검증할 수 있다.

### 권장

기본 주소 geocode에는 넣지 않는다. `match_kind="place"` 또는 별도 admin/POI 검색 feature가 필요할 때 분리해 도입한다.

## 과거 snapshot

현재 디렉터리에는 과거 snapshot도 있다.

- `202603_도로명주소 한글_전체분(1).zip`
- `202603_상세주소DB_전체분.zip`
- `202604_상세주소DB_전체분.zip`
- `202604_주소DB_전체분.zip`

### 정확도 개선 가능성

최신 serving 정확도 개선에는 낮다. 과거 기준월 데이터는 최신 snapshot을 대체하면 regression이 된다.

### 검증용 가치

중간이다.

- 기준월 변경 전후 row-count drift
- 일변동 적용 결과 검증
- `source_yyyymm` 혼합 적재 경고 테스트
- 백업/리스토어 manifest의 reproducibility 테스트

### 권장

serving 원천으로 쓰지 않는다. regression fixture 또는 migration/restore 검증용으로만 쓴다.

## 도입 우선순위

1. `도로명주소 출입구 정보`
   - 이미 loader가 있다.
   - `juso=202605`와 내부 `RNENTDATA_2605_*`를 맞추면 direct entrance 승격 조건을 만족할 수 있다.
   - 대표 좌표 정확도에 가장 직접적이다.

2. `도로명주소 건물 도형`의 `TL_SPBD_ENTRC`, `TL_SPOT_CNTC`
   - 출입구 point와 연결선 검증으로 C2/C4/C8 설명력을 높일 수 있다.
   - 별도 analysis table부터 시작한다.

3. `건물군 내 상세주소 동 도형` + `상세주소DB`
   - 일반 geocode보다 상세주소 기능 후보로 묶는다.
   - `match_kind="detail"` 또는 별도 endpoint를 검토한다.

4. `국가지점번호 중심점`
   - 10m 좌표 개선용이 아니라 parser/formatter 검증용으로 먼저 쓴다.
   - 100m prefix 지원을 추가할 때 feature flag로 검토한다.

5. `국가지점번호 도형`
   - grid overlay와 offline validation 중심으로 둔다.
   - 100m polygon 1천만 건은 상시 serving DB 적재를 피한다.

6. `건물DB`, `주소DB`
   - 좌표 개선보다 consistency와 기준월/키 drift 검증에 먼저 쓴다.

7. `민원행정기관전자지도`
   - POI/기관 검색 요구가 생기면 별도 feature로 분리한다.

## 구현 시 주의점

- 새 좌표 후보를 `mv_geocode_target`에 넣을 때는 `pt_source` coarse enum(`entrance`/`centroid`)을 확장하지 않고, 세부 원천은 `coord_source_detail`로 분리한다(ADR-055). priority와 gate는 별도 문서에 남긴다.
- 같은 건물에 여러 출입구 후보가 있을 때 `source_kind`, 기준월, distance-to-road, polygon containment를 scoring feature로 분리한다.
- `TL_SGCO_RNADR_MST`와 `TL_SPBD_BULD`는 의미가 다르므로 같은 테이블에 덮어쓰지 않는다.
- `TL_SPBD_ENTRC`가 여러 원천에 있으므로 전자지도, 건물 도형 bundle, direct entrance, locsum의 우선순위를 먼저 정한다.
- 상세주소 계열은 일반 주소 결과에 자동으로 붙이지 않는다. 입력에 상세주소가 있을 때만 별도 후보로 둔다.
- 국가지점번호 grid/center는 현재 10m parser보다 coarser한 원천이다. 정밀도 개선이라고 표시하면 안 된다.
- 100m grid polygon과 100m center는 데이터 규모가 크므로 loader보다 streaming validation을 먼저 만든다.
- 모든 선택 원천은 `source_yyyymm`과 내부 member 기준월이 다를 수 있다. 예: `도로명주소 출입구 정보\202604`의 내부 파일은 `RNENTDATA_2605_*`다.

## 다음 작업 후보

| 후보 | 산출물 | 성공 기준 |
|------|--------|-----------|
| 출입구 후보 통합 분석 | `scripts/compare_entrance_sources.py` | locsum/direct/electronic/building-bundle entrance 거리 분포와 source priority 제안 |
| 국가지점번호 검증 harness | `scripts/validate_sppn_grid.py` | 100m center TXT와 parser parent prefix 계산 일치 |
| 상세주소 실험 loader | `tl_detail_dong_polygon`, `tl_detail_dong_entrc` staging | 상세주소DB key overlap과 geometry containment report |
| 건물 도형 analysis loader | `tl_roadaddr_buld_*` staging | `TL_SGCO_RNADR_MST`/`TL_SPBD_BULD` overlap 전국 재측정 |
| 기타 텍스트 consistency | 주소DB/건물DB row-count/key drift report | `tl_juso_text`, `tl_juso_parcel_link`, `tl_spbd_buld_polygon`과 차이 목록 |
