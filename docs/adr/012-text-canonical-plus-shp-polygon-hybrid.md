# ADR-012: 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드로 한다

- 상태: accepted (ADR-005를 부분 supersede)
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
첨부 사양서는 도로명주소 전자지도(SHP) 11개 마스터를 1차 데이터로 가정했다. 그러나 행안부는 같은 정보를 텍스트 정본 3종으로도 제공하며, **텍스트가 raw 정본**이고 SHP은 도형 적재용으로 가공된 파생물이다.

| 자료 | 정본성 | 무엇이 들어있는가 |
|------|--------|-------------------|
| 도로명주소 한글_전체분 (월간) | 도로명주소·지번·우편번호·법정동·행정동의 **정본** | 좌표 없음. BD_MGT_SN ↔ 행정 매핑이 가장 완전 |
| 위치정보요약DB_전체분 (월간) | 출입구 좌표(EPSG:5179)의 **정본** | BD_MGT_SN + ent_man_no, ent_se_cd 명확 |
| 내비게이션용DB_전체분 (월간) | 내비 진입점·차량 진입점·건물 centroid의 **정본** | 출입구가 없는 건물의 fallback 좌표 |
| 도로명주소 전자지도 SHP (월간) | **polygon/폴리라인의 정본** | 행정구역·우편번호·건물·도로 도형 |

SHP만으로는 행정동 코드(`adm_cd`, vworld 응답 `level4A`/`level4AC`)와 출입구 분류가 충분하지 않다. ADR-005가 GDAL VectorTranslate로 모든 적재를 묶었던 결정은 사양 완성도 측면에서 손해다.

## 결정
**적재를 두 경로로 분리한다.**

| 경로 | 대상 | 도구 | 의존성 |
|------|------|------|--------|
| **텍스트 1차** (`loaders/text/`) | `tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc` | stdlib `csv` + `psycopg.copy()` | GDAL 불필요 |
| **텍스트 선택 보조** (`loaders/text/`) | `tl_roadaddr_entrc` | stdlib `csv` + `psycopg.copy()` | T-039 이후 direct 출입구 선택 적재 |
| **SHP 보조** (`loaders/shp/`) | `tl_scco_ctprvn/sig/emd/li`, `tl_kodis_bas`, `tl_spbd_buld_polygon`, `tl_sprd_manage/intrvl/rw` | GDAL Python binding (ADR-005 한정 유지) | `libgdal-dev` |

`tl_spbd_buld_polygon`은 BD_MGT_SN PK만 공유하고 **속성은 모두 `tl_juso_text`에서** 채운다 — 도형과 속성의 책임을 명확히 분리.

`mv_geocode_target`은 텍스트 1차 + 출입구 좌표 + centroid fallback을 합쳐 구성한다(`docs/architecture/data-model.md`). `pt_source ∈ {entrance, centroid}` 컬럼으로 응답에 좌표 출처를 노출한다. T-039 이후 direct 출입구와 위치정보요약DB 출입구는 모두 호환성상 `entrance`로 분류하고, 세부 원천은 운영 테이블과 정합성 sample에서 추적한다.

## 근거
- **정본 우선**: 행정동 코드, 도로명 텍스트, 우편번호 정본이 모두 텍스트에서 raw로. SHP DBF에 의존하지 않음.
- **GDAL 의존성 축소**: 텍스트 적재는 stdlib만으로 동작. GDAL 환경 셋업 실패가 전체 적재를 막지 않음(polygon만 GDAL 필요).
- **출입구 0개 건물 fallback**: 내비게이션용DB centroid가 빈자리를 메움 — 사양에 fallback 경로가 자연스럽게 박힘.
- **v1 코드 경험**: v1 `store.py`/`data.py`가 이 세 텍스트를 이미 다뤘음 — 컬럼 매핑·CP949 디코딩 노하우를 reference로.

## 결과(긍정)
- 응답 완성도 ↑ — 행정동 정보가 vworld 호환 응답 전체에 자연스럽게.
- 적재 환경 의존성 감소 — GDAL 없이도 80% 적재 가능. polygon만 GDAL.
- 출입구 없는 건물의 fallback이 사양 단계에서 해결.
- 텍스트와 SHP 사이의 BD_MGT_SN 정합성 검증으로 데이터 무결성 회귀 감지.

## 결과(부정)
- 마스터 테이블 종류 증가(11 → 14). MV 정의 복잡도 ↑(단 라우터는 MV만 보면 됨).
- 두 변동분(텍스트 월간 + SHP polygon 월간) 기준일 정합성 운영 책임 추가 — `load_manifest`에 `source_set` 표기로 해결.
- 라이선스 표시 의무(공공누리 1형) — 운영 README/응답 메타에 명시.

## 후속
- (open) ADR-005의 GDAL Python binding 결정은 polygon 적재에만 한정 — 본문 supersede 표시 완료.
- (open) 텍스트 변동분(`도로명주소 한글_변동분`, `위치정보요약DB_변동분`)의 누적 적용 정책은 ADR-009(우편번호) 모델 따라 분기 풀로드만 운영하는 옵션 검토.
- (open) 정합성 검증 리포트(`docs/architecture/data-model.md` "정합성 검증")의 임계값(예: 좌표 오차 95th percentile < 5m)을 실데이터로 캘리브레이션.
