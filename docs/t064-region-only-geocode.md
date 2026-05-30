# T-064 상위 주소 geocode 후보

`/v2/geocode`는 별도 행정구역 전용 endpoint를 만들지 않고, 기존 후보형 응답 안에서 상위 주소 입력을 처리한다. 사용자가 `수지구`, `용인시 수지구`, `성복동`처럼 건물번호나 지번 없이 행정구역까지만 입력하면 일반 주소 parser가 번호 부재로 실패한 뒤, 내부적으로 `search(type="district")` 결과를 geocode candidates로 승격한다.

## 동작 원칙

- 상세 주소가 있으면 기존 도로명/지번 geocode 경로를 먼저 사용한다.
- 상세 번호가 없어 주소 parser가 `InvalidAddressError`를 내면 같은 입력으로 `district` 검색을 수행한다.
- 후보는 기존 `CandidateV2`를 그대로 사용한다.
  - `match_kind="region"`
  - `source="local"`
  - `point`는 행정구역 polygon의 `ST_PointOnSurface` 결과
  - `region.sig_cd`/`region.bjd_cd`는 코드 길이에 맞게 채운다.
- `ST_Centroid` 대신 `ST_PointOnSurface`를 사용한다. 지도 중심으로 보기에는 centroid가 직관적일 수 있지만, 다중 polygon이나 오목 polygon에서 polygon 밖으로 나갈 수 있어 사용자 선택 후보 대표점은 내부점을 우선한다.

## 사용 데이터

현재 구현은 이미 full-load에 포함되는 전자지도 행정구역 polygon을 사용한다.

| 입력 범위 | 테이블 | 코드 |
|---|---|---|
| 시도 | `tl_scco_ctprvn` | `ctprvn_cd` 2자리 |
| 시군구 | `tl_scco_sig` | `sig_cd` 5자리 |
| 읍면동 | `tl_scco_emd` | `emd_cd` 8자리 |
| 리 | `tl_scco_li` | `li_cd` 10자리 |

예를 들어 `수지구`는 `tl_scco_sig.sig_kor_nm='용인시 수지구'` 후보가 우선 반환되고, 같은 이름을 포함하는 하위 법정동 후보가 뒤따른다. 실제 Docker DB 기준 첫 후보는 `sig_cd=41465`, 대표점은 약 `(127.08875165616607, 37.3327969096687)`이다.

## 내비게이션용DB 후속 보강

사용자 지시에 따라 상위 주소 후보 기능은 행정구역 polygon만으로 끝내지 않는다. `내비게이션용DB_전체분`도 검색 품질에 직접 사용해야 하며, 특히 원천의 `시군구용건물명` 칼럼을 검색 후보에 포함해야 한다.

T-065에서 이 후속을 구현했다. `navi_loader.py`는 `match_build_*.txt`의 20번째 컬럼을 `sigungu_buld_nm`으로 보존하고, generated column `sigungu_buld_nm_nrm`을 `mv_geocode_target`과 `mv_geocode_text_search`에 전달한다. `v2/search`는 `rn_nrm`/`buld_nm_nrm`뿐 아니라 `sigungu_buld_nm_nrm`도 exact preflight와 broad trigram fallback에서 사용한다.

실제 202604 전국 파일 기준 `시군구용건물명` non-empty row는 `773,407 / 10,721,310`건이고 distinct 값은 `77,790`개다. 변경 전 `NOT_FOUND`였던 `엄마집`, `P-101동` + `sig_cd=26110` 검색은 변경 후 후보를 반환한다. 상세한 컬럼 위치, 적재 시간, helper MV 크기, 전후 recall/latency는 `docs/t065-navi-building-name-search.md`에 기록했다.

이 후속은 새 외부 원천을 뜻하지 않는다. 이미 쓰는 `내비게이션용DB_전체분`을 더 완전하게 적재하고 검색 인덱스에 반영하는 작업이다.
