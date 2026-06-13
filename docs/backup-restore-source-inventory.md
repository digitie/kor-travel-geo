# 백업/리스토어 원천 데이터 인벤토리

이 문서는 백업/리스토어 로직을 정교하게 만들 때 필요한 "어떤 파일과 API 소스를 로드해 어떤 DB 상태를 만들었는가"를 정리한다. 핵심은 `pg_dump` artifact만으로는 재현성이 부족하므로, 별도 `source_set` manifest에 원천 파일, 기준월, checksum, object storage 위치, 적용 순서, 파생 MV 상태를 함께 남기는 것이다.

## 범위

- 기준 코드: `src/kortravelgeo/infra/source_set.py`, `src/kortravelgeo/loaders/**`
- 기준 문서: `docs/t027-fullload-plan.md`, `docs/external-apis.md`, `docs/backend-package.md`
- 현재 연결 DB 관찰일: 2026-06-14
- PostgreSQL/RustFS 생명주기는 이 저장소가 직접 관리하지 않고, 접속 설정만 사용한다.

## Full-load 필수 파일 원천

`SourceSetPlan`의 필수 source kind는 `juso`, `parcel_link`, `locsum`, `navi`, `shp` 다섯 가지다.

| source kind | 원천 파일/패턴 | 주요 적재 테이블 | 비고 |
|-------------|----------------|------------------|------|
| `juso` | `도로명주소 한글_전체분/rnaddrkor_*.txt` | `tl_juso_text` | 도로명주소 텍스트 정본. `bd_mgt_sn` 기준 upsert |
| `parcel_link` | `도로명주소 한글_전체분/jibun_rnaddrkor_*.txt` | `tl_juso_parcel_link` | 건물-지번 1:N 보조 관계. `tl_juso_text.pnu`를 덮어쓰지 않음 |
| `locsum` | `위치정보요약DB` ZIP/member 또는 디렉터리의 `entrc_*.txt` | `tl_locsum_entrc` | EPSG:5179 출입구 좌표. 좌표 결측 행은 적재하지 않음 |
| `navi` | `내비게이션용DB/match_build_*.txt` | `tl_navi_buld_centroid` | 건물 centroid fallback과 `시군구용건물명` 검색 보강 |
| `navi` | `내비게이션용DB/match_rs_entrc.txt` | `tl_navi_entrc` | 내비/차량/부속 출입구 보조 |
| `shp` | 도로명주소 전자지도 시도별 SHP 디렉터리 또는 원본 ZIP | `tl_scco_*`, `tl_kodis_bas`, `tl_sprd_*`, `tl_spbd_buld_polygon` | 도형 전용 보조 원천. 현 로더 직접 입력은 압축 해제된 시도 디렉터리 |

텍스트 원천 인코딩은 BOM이 있으면 `utf-8-sig`, 그 외에는 CP949 기본 전략을 사용한다. 모든 로더는 가능한 경우 `source_file`, `source_yyyymm`을 row에 보존한다.

## 현재 로컬 원본 배치

2026-06-14 재확인 기준 로컬 원본 기준 경로는 `F:\dev\kor-travel-geo\data\juso`다. 압축파일 원본 기준으로 필요한 핵심 묶음은 다음과 같이 들어 있다.

| source kind | 현재 원본 경로 | 확인 내용 | 기준년월 추출 |
|-------------|----------------|-----------|---------------|
| `juso` | `202605_도로명주소 한글_전체분.zip` | `rnaddrkor_*.txt` 17개 | 파일명 `202605` |
| `parcel_link` | `202605_도로명주소 한글_전체분.zip` | `jibun_rnaddrkor_*.txt` 17개 | 파일명 `202605` |
| `locsum` | `202604_위치정보요약DB_전체분.zip` | `entrc_*.txt` 17개 | 파일명 `202604` |
| `navi` | `202604_내비게이션용DB_전체분.7z` | `match_build_*.txt` 17개, `match_rs_entrc.txt` 1개, `match_jibun_*.txt` 17개 | 파일명 `202604` |
| `shp` | `도로명주소 전자지도\202604\<시도>.zip` 17개 | serving 대상 9개 layer의 `.shp/.shx/.dbf` sidecar 모두 존재 | 상위 디렉터리 `202604`. 개별 ZIP 파일명만으로는 불가 |
| `roadaddr_entrance` | `도로명주소 출입구 정보\202604\<시도>.zip` 17개 | 각 ZIP 내부 `RNENTDATA_2605_<시도코드>.txt` 1개 | 내부 파일명 기준 `202605`. 상위 디렉터리 `202604`와 다름 |
| `sppn_makarea` | `구역의도형\202603\<시도>.zip` 17개 | `TL_SPPN_MAKAREA.{shp,shx,dbf}` 모두 존재 | 상위 디렉터리 `202603`. 개별 ZIP 파일명만으로는 불가 |

`도로명주소 전자지도\202604\<시도>.zip`에는 `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`, `TL_SPRD_MANAGE`, `TL_SPRD_INTRVL`, `TL_SPRD_RW`, `TL_SPBD_BULD`가 모두 들어 있다. 예를 들어 `서울특별시.zip`은 `11000/TL_SPBD_BULD.shp` 같은 내부 경로를 가진다.

주의할 점은 두 가지다. 첫째, `navi` 원본은 7z라서 현 텍스트 로더가 직접 읽는 ZIP/TXT 입력 형태로 압축 해제가 필요하다. 둘째, `shp` 전자지도 원본도 ZIP으로 보관되어 있으므로 현 `shp_polygons_loader`에 넣으려면 `도로명주소 전자지도\202604\<시도명>\<시도코드>\TL_*.{shp,shx,dbf}` 형태로 materialize해야 한다.

## 현재 디렉터리 기준 사용/미사용 구분

`F:\dev\kor-travel-geo\data\juso` 현재 배치에서, 현행 서빙 DB를 재구성할 때 쓰는 파일과 쓰지 않는 파일은 다음처럼 구분한다.

정확도 개선 또는 검증용 활용 가능성은 `docs/source-data-accuracy-review.md`에 더 자세히 정리한다.

### 기본 full-load 사용

| 경로 | 사용 source kind | 사용 내용 | 주의점 |
|------|------------------|-----------|--------|
| `202605_도로명주소 한글_전체분.zip` | `juso`, `parcel_link` | `rnaddrkor_*.txt`, `jibun_rnaddrkor_*.txt` | 현재 디렉터리 기준 최신 도로명주소 텍스트 정본 |
| `202604_위치정보요약DB_전체분.zip` | `locsum` | `entrc_*.txt` | ZIP 직접 읽기 가능 |
| `202604_내비게이션용DB_전체분.7z` | `navi` | `match_build_*.txt`, `match_rs_entrc.txt` | 7z 압축 해제 후 로더 입력. `match_jibun_*.txt`는 현재 로더가 쓰지 않음 |
| `도로명주소 전자지도\202604\<시도>.zip` | `shp` | serving 대상 9개 SHP layer | ZIP materialize 필요. 기준월은 상위 디렉터리 `202604`에서 추출 |

전자지도 ZIP에서 현재 serving full-load가 쓰는 layer는 다음 9개다.

- `TL_SCCO_CTPRVN`
- `TL_SCCO_SIG`
- `TL_SCCO_EMD`
- `TL_SCCO_LI`
- `TL_KODIS_BAS`
- `TL_SPRD_MANAGE`
- `TL_SPRD_INTRVL`
- `TL_SPRD_RW`
- `TL_SPBD_BULD`

### 선택/조건부 사용

여기서 "선택"은 `SourceSetPlan`의 필수 원천(`juso`, `parcel_link`, `locsum`, `navi`, `shp`)은 아니지만 파일을 주면 별도 loader가 적재할 수 있다는 뜻이다. "조건부"는 DB에는 적재되더라도 일반 주소 geocode/reverse serving 경로에 항상 반영되는 것은 아니고, 기준월 일치나 입력 주소 종류 같은 조건을 만족할 때만 결과에 쓰인다는 뜻이다.

| 경로 | 사용 source kind | 사용 내용 | 주의점 |
|------|------------------|-----------|--------|
| `도로명주소 출입구 정보\202604\<시도>.zip` | `roadaddr_entrance` | `RNENTDATA_2605_<시도코드>.txt` | 내부 파일명 기준월은 `202605`. 현재 `juso=202605`와 맞추면 direct 출입구 좌표 후보로 승격 가능 |
| `구역의도형\202603\<시도>.zip` | `sppn_makarea` | `TL_SPPN_MAKAREA.{shp,shx,dbf}` | 국가지점번호 geocode/reverse 보조. 같은 ZIP의 중복 행정구역 layer는 현재 기본 load에 쓰지 않음 |

### 현재 기본 서빙 load에서 쓰지 않음

| 경로 | 이유 |
|------|------|
| `202603_도로명주소 한글_전체분(1).zip` | 과거 snapshot. 현재 디렉터리 기준으로는 `202605_도로명주소 한글_전체분.zip`을 사용 |
| `202603_상세주소DB_전체분.zip` | 현재 serving loader 없음 |
| `202604_상세주소DB_전체분.zip` | 현재 serving loader 없음 |
| `202605_상세주소DB_전체분.zip` | 현재 serving loader 없음 |
| `202604_주소DB_전체분.zip` | 현재 full-load 정본은 `도로명주소 한글_전체분`/`위치정보요약DB`/`내비게이션용DB`/전자지도 조합이라 이 ZIP은 쓰지 않음 |
| `202605_주소DB_전체분.zip` | 현재 serving loader 없음 |
| `202605_건물DB_전체분.zip` | 현재 serving loader 없음 |
| `도로명주소 건물 도형\202604\<시도>.zip` | T-040 분석 후보. `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC` bundle은 현행 `tl_spbd_buld_polygon`에 섞지 않음 |
| `건물군 내 상세주소 동 도형\202604\<시도>.zip` | T-041 분석 후보. 전자지도 건물 polygon 부분집합으로 판단되어 기본 serving load에는 쓰지 않음 |
| `국가지점번호 도형\202405\*.zip` | 현재 국가지점번호 서빙은 parser와 `TL_SPPN_MAKAREA`를 사용하며 grid 도형 ZIP은 쓰지 않음 |
| `국가지점번호 중심점\202405\*.zip` | 현재 loader 없음 |
| `민원행정기관전자지도_240124.zip` | 현재 serving loader 없음 |

전자지도 ZIP 내부에 `TL_SPBD_EQB`, `TL_SPBD_ENTRC`가 있어도 현재 serving full-load 대상은 아니다. 필요하면 별도 source kind와 테이블 계약을 정의해야 한다.

## SHP 적재 대상

도로명주소 전자지도 discovery는 더 많은 layer를 볼 수 있지만, serving 보조 적재 대상은 다음 9개 layer로 제한된다.

| SHP layer | 적재 테이블 | 용도 |
|-----------|-------------|------|
| `TL_SCCO_CTPRVN` | `tl_scco_ctprvn` | 시도 polygon |
| `TL_SCCO_SIG` | `tl_scco_sig` | 시군구 polygon |
| `TL_SCCO_EMD` | `tl_scco_emd` | 읍면동 polygon |
| `TL_SCCO_LI` | `tl_scco_li` | 리 polygon |
| `TL_KODIS_BAS` | `tl_kodis_bas` | 기초구역/우편번호 polygon |
| `TL_SPRD_MANAGE` | `tl_sprd_manage` | 도로 관리 LineString |
| `TL_SPRD_INTRVL` | `tl_sprd_intrvl` | 기초번호 구간 DBF 속성. T-034 이후 DBF direct COPY |
| `TL_SPRD_RW` | `tl_sprd_rw` | 도로 폭/구간 도형 |
| `TL_SPBD_BULD` | `tl_spbd_buld_polygon` | 건물 polygon |

`TL_SPBD_EQB`, `TL_SPBD_ENTRC`는 discovery 대상이지만 현재 full-load serving 적재 대상은 아니다. 별도 활용이 필요하면 source kind와 테이블 계약을 새로 정해야 한다.

## 선택 파일 원천

| source kind | 원천 파일/패턴 | 적재 테이블 | 복원/서빙 주의점 |
|-------------|----------------|-------------|------------------|
| `roadaddr_entrance` | `도로명주소 출입구 정보/RNENTDATA_*.txt` 또는 ZIP 내부 | `tl_roadaddr_entrc` | direct `bd_mgt_sn + EPSG:5179` 출입구. `source_yyyymm`이 `tl_juso_text.source_yyyymm` 집합과 같을 때만 MV fallback 후보 |
| `sppn_makarea` | `구역의 도형` ZIP/SHP 내부 `TL_SPPN_MAKAREA.{shp,shx,dbf}` | `tl_sppn_makarea` | 국가지점번호 geocode/reverse 보조 |
| `pobox` | epost ZIP 추출본 중 `사서함` 또는 `pobox` 파일명 | `postal_pobox` | 현재 운영 DB에는 0행일 수 있음 |
| `bulk` | epost ZIP 추출본 중 `다량`, `대량`, `bulk`, `delivery` 파일명 | `postal_bulk_delivery` | 현재 운영 DB에는 0행일 수 있음 |

현재 로컬 자료 조합에서는 `roadaddr_entrance=202605`, `tl_juso_text=202603`이라 direct 출입구는 DB에는 보존되지만 `mv_geocode_target` 좌표에는 승격되지 않는다.

## 일변동 ZIP

일변동 ZIP은 full snapshot 이후 별도 delta로 적용한다.

| ZIP member | 처리 로더 | 적재 대상 |
|------------|-----------|-----------|
| `AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT` | `load_daily_juso_delta` | `tl_juso_text` upsert/delete |
| `AlterD.JUSUKR.*.TH_SGCO_RNADR_LNBR.TXT` | `load_daily_parcel_link_delta` | `tl_juso_parcel_link` upsert/delete |

`MVM_RES_CD`는 settings 또는 `load_codes` 계열 설정으로 action을 해석한다. 백업 manifest에는 사용한 코드 매핑과 `last_mvmn_de`를 반드시 남겨야 한다.

## 파생 서빙 객체

파일 원천에서 직접 오는 source of truth와, 재생성 가능한 serving accelerator를 구분한다.

| 객체 | 성격 | 재생성 기준 |
|------|------|-------------|
| `mv_geocode_target` | geocode/reverse 기본 serving MV | `tl_juso_text` + `tl_locsum_entrc` + same-month `tl_roadaddr_entrc` + `tl_navi_buld_centroid` |
| `mv_geocode_text_search` | fuzzy 검색 helper MV | `mv_geocode_target`에서 재생성 |
| `region_radius_parts` | 행정구역 반경조회 accelerator | `tl_scco_ctprvn/sig/emd`에서 `ST_Subdivide`로 재생성 |

복원 로직은 dump에 MV data를 포함할지 여부와 별개로, MV SQL hash와 refresh/swap 방식, row count를 manifest에 남겨야 한다. `mv_geocode_target`만 단독 refresh하면 helper MV와 세대가 어긋날 수 있으므로 `ktgctl refresh mv` 또는 admin maintenance 경로를 사용한다.

## 외부 API 소스

외부 API는 두 부류로 나뉜다. VWorld/Juso는 조회 폴백이고, epost는 오프라인 파일 원천을 만드는 다운로드 API다.

| API | 기본 URL/설정 | 용도 | DB bulk 원천 여부 |
|-----|---------------|------|------------------|
| VWorld OpenAPI | `KTG_VWORLD_URL=https://api.vworld.kr/req/address` | 로컬 geocode `NOT_FOUND` 뒤 `fallback="api"` 1차 폴백 | 아님 |
| Juso 검색 | `KTG_JUSO_SEARCH_URL=https://business.juso.go.kr/addrlink/addrLinkApi.do` | VWorld 실패/미설정 뒤 주소 검색 폴백 | 아님 |
| Juso 좌표 | `KTG_JUSO_COORD_URL=https://business.juso.go.kr/addrlink/addrCoordApi.do` | Juso 검색 결과의 좌표 변환 | 아님 |
| epost 우편번호 다운로드 | `KTG_EPOST_DOWNLOAD_URL=.../downloadAreaCodeService/getAreaCodeInfo` | `downloadKnd=1` 전체 ZIP 다운로드 후 `postal_*` 적재 | 파일 원천 생성용 |
| VWorld WMTS | `https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{z}/{y}/{x}.{ext}` | 디버그 UI 지도 타일 | 아님 |

VWorld/Juso 응답은 로컬 DB 결과가 없을 때만 후보 응답으로 섞이며, 현재 DB backup source of truth로 취급하지 않는다. 반대로 epost는 API 응답 자체가 ZIP 파일 원천이므로 다운로드 URL, `downloadKnd`, ZIP checksum, 추출 파일 checksum을 기록해야 한다.

## RustFS의 위치

RustFS는 주소 데이터 제공자가 아니라 upload set 저장소다. RustFS upload set은 기존 로더가 파일 시스템 path를 읽을 수 있도록 materialized cache로 내려받아 처리한다.

백업/리스토어 manifest에는 다음을 남긴다.

- `storage_kind`: `local` 또는 `rustfs`
- `storage_uri`: 예: `rustfs://<bucket>/<prefix>/uploads/<upload_set_id>/...`
- object key, etag, size, optional sha256
- materialized cache path와 cache checksum
- bucket, prefix, endpoint 식별자. access/secret key는 남기지 않고 fingerprint만 선택적으로 남긴다.

## 현재 연결 DB 관찰 예

2026-06-14 현재 `.env`의 `KTG_PG_DSN`이 가리키는 `kor_travel_geo`에서 관찰한 대표 상태다.

| 테이블/뷰 | 행 수 | 기준월 |
-----------|------:|--------|
| `tl_juso_text` | 6,416,637 | `202603` |
| `tl_juso_parcel_link` | 1,769,370 | `202603` |
| `tl_locsum_entrc` | 6,405,091 | `202604` |
| `tl_roadaddr_entrc` | 6,404,697 | `202605` |
| `tl_navi_buld_centroid` | 10,687,317 | `202604` |
| `tl_navi_entrc` | 12,830 | `202604` |
| `tl_spbd_buld_polygon` | 10,687,732 | `202604` |
| `tl_sppn_makarea` | 24,204 | `202605` |
| `region_radius_parts` | 54,316 | 파생 |
| `mv_geocode_target` | 6,416,637 | 파생 |
| `mv_geocode_text_search` | 6,416,637 | 파생 |
| `postal_pobox` | 0 | 없음 |
| `postal_bulk_delivery` | 0 | 없음 |

`mv_geocode_target.pt_source` 분포는 `entrance=2,906,372`, `centroid=3,496,182`, `NULL=14,083`이다. direct `tl_roadaddr_entrc`는 same-month 조건을 만족하지 않아 현재 좌표 승격에는 쓰이지 않는다.

## 백업 manifest 권장 필드

정교한 백업/리스토어 artifact는 최소한 다음 정보를 함께 가져야 한다.

| 영역 | 권장 필드 |
------|-----------|
| 코드/스키마 | git SHA, package version, Alembic head, `SCHEMA_SQL`/`INDEX_SQL`/`MV_SQL` hash |
| DB dump | profile, format, jobs, compression, dump 시작/종료 시각, source DB 식별자, row count snapshot |
| source set | `source_set_id`, `yyyymm_by_kind`, `mixed_yyyymm`, 확인자, 확인 시각, confirmation hash |
| 원천별 파일 | source kind, loader job kind, path 또는 `storage_uri`, file count, byte size, sha256/etag, source member 목록 |
| 원천별 적재 | target tables, row count, `source_yyyymm`, `source_file` 채움 여부, `last_mvmn_de`, `MVM_RES_CD` action mapping |
| 외부 API | 사용한 provider URL, provider 종류, key fingerprint, 호출 목적. secret 원문은 저장 금지 |
| 파생 객체 | MV/accelerator 이름, row count, size, definition hash, refresh 방식, active release id |
| 검증 | smoke 주소와 결과, C1~C10 `severity_max`, `pt_source` 분포, 대표 query benchmark run id |

리스토어 후에는 `load_manifest`, `ops.dataset_snapshots`, `ops.serving_releases`, MV row count, `pt_source` 분포, C10 기준월 evidence를 먼저 대조한다. 이 값이 맞지 않으면 DB dump 자체가 복원됐더라도 동일한 서빙 데이터셋이라고 보기 어렵다.
