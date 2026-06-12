// 운영자가 PostgreSQL 물리 테이블 이름만 보고 의미를 알기 어렵기 때문에,
// 각 테이블이 담는 데이터를 한글로 설명한다. 새 테이블이 추가되면 여기 항목을 더한다.
const TABLE_DESCRIPTIONS: Record<string, string> = {
  tl_juso_text: "도로명주소 한글 정본 (건물 단위 주소 본문)",
  tl_juso_parcel_link: "도로명주소 ↔ 지번(PNU) 연결",
  tl_roadaddr_entrc: "도로명주소 출입구 정보",
  tl_locsum_entrc: "위치정보요약DB 출입구/대표 좌표",
  tl_navi_buld_centroid: "내비게이션용DB 건물 중심점 좌표",
  tl_navi_entrc: "내비게이션용DB 진입점/부속 출입구",
  tl_spbd_buld_polygon: "건물 도형(폴리곤) 보조 레이어",
  tl_sppn_makarea: "국가지점번호 표기 의무지역",
  tl_scco_ctprvn: "행정구역 경계 - 시도",
  tl_scco_sig: "행정구역 경계 - 시군구",
  tl_scco_emd: "행정구역 경계 - 읍면동",
  tl_scco_li: "행정구역 경계 - 리",
  tl_kodis_bas: "기초구역(우편번호 구역) 경계",
  tl_sprd_manage: "도로구간 관리(도로명) 도형",
  tl_sprd_rw: "도로 실폭(도로 면) 도형",
  tl_sprd_intrvl: "도로구간 구간정보",
  postal_pobox: "사서함 우편번호",
  postal_bulk_delivery: "대량배달처 우편번호",
  geo_cache: "외부 API 지오코딩 결과 캐시",
  load_jobs: "적재/운영 작업 큐와 진행 상태",
  load_codes: "코드 매핑 테이블",
  load_manifest: "적재 원천 파일 매니페스트",
  load_consistency_reports: "C1~C10 정합성 검증 리포트",
  mv_geocode_target: "지오코딩 서빙용 통합 MV (대표 좌표)",
  mv_geocode_text_search: "텍스트 검색 보조 MV"
};

export function tableDescription(tableName: string): string {
  if (TABLE_DESCRIPTIONS[tableName]) {
    return TABLE_DESCRIPTIONS[tableName];
  }
  if (tableName.startsWith("ops_") || tableName.startsWith("ops.")) {
    return "운영 메타데이터 (스냅샷/릴리스/감사 등)";
  }
  return "—";
}
