# 스테이징 full-load (blue-green) 런북 — T-290j

Dagster `full_load_batch`를 **serving DB를 건드리지 않고** 격리된 스크래치 DB로 실행·검증하는
절차. serving MV(`mv_geocode_target`/`tl_juso_text`)는 열지 않는다.

## 설계 (왜 blue-green인가)

`run_full_load_batch`는 제어면(`load_jobs`/`ops.*`·consistency 리포트·mv-release)과 데이터면
(`tl_juso_text`/`mv_geocode_target`·MV swap)을 **한 엔진**으로 처리한다. 그래서 스테이징은
"전체 DAG를 스크래치 엔진에서 실행" — 스크래치 DB를 full-schema 클론으로 초기화한 뒤 그 안에서만
로드·swap한다. `payload.target_database`가 그 스위치다.

- API 런처(`_full_load_launch.launch_full_load_batch_dagster_run`)가 `target_database`를 보면
  `ensure_scratch_database`(= `ktgctl init-db` 시퀀스: SCHEMA_SQL+INDEX_SQL+MV_SQL+consistency
  registry)로 스크래치 DB를 만들고, root/child `load_jobs` 행을 **스크래치 엔진**에 넣는다.
- Dagster op(`run_full_load_batch_op`)이 같은 `target_database`로 스크래치 엔진을 해석해
  `execute_load_job`(adopt/lease/heartbeat)와 `run_full_load_batch`(DAG) 양쪽에 넘긴다. run 종료 시
  엔진 dispose.

## 사전 조건

1. **소스 데이터** — 전국 원천(JUSO 한글 전체분 + LOCSUM + NAVI + SHP polygons + pobox)을 배포
   호스트(n150)의 `KOR_TRAVEL_GEO_SOURCE_DIR`(기본 `/home/digitie/kor-travel-geo-data/source`)에
   배치. 파일 구동 로드는 `batch_payload`의 절대경로(`/app/data/source/...`)를 읽는다.
2. **공유 볼륨** — `docs/deploy/docker-compose.geo-source-vol.yml`을 docker-manager에 넣고
   추가 `-f`로 재배포해 api+dagster+dagster-daemon이 `/app/data/source`(+`/app/data/rustfs/
   materialized`)를 공유하게 한다.
3. **GDAL dagster 이미지** — T-290j에서 배포됨(GDAL 3.10.3 in-container 확인).

## 실행

```bash
# 1) full_load_batch를 Dagster로 라우팅 (.env)
#    KOR_TRAVEL_GEO_DAGSTER_EXECUTED_JOB_KINDS=db_backup,db_restore,full_load_batch
#    → api/dagster 재배포

# 2) 스테이징 full_load_batch 제출 (target_database + 파일 구동 children).
#    payload 예 (source 절대경로는 /app/data/source/... 기준):
curl -sS -X POST http://127.0.0.1:12501/admin/loads \
  -H "content-type: application/json" \
  -H "x-ktg-admin-proxy-secret: $KTG_ADMIN_PROXY_SECRET" \
  -H "x-ktg-actor: staging-e2e" -H "x-ktg-roles: rebuild_operator" \
  -d '{"kind":"full_load_batch","payload":{
        "target_database":"kor_travel_geo_fullload_e2e",
        "source_yyyymm":"<JUSO_YYYYMM>",
        "payloads":{
          "juso_text_load":{"path":"/app/data/source/juso/..."},
          "juso_parcel_link_load":{"path":"/app/data/source/juso/..."},
          "locsum_load":{"path":"/app/data/source/locsum/..."},
          "navi_load":{"path":"/app/data/source/navi/..."},
          "shp_polygons_load":{"path":"/app/data/source/shp/..."},
          "pobox_load":{"path":"/app/data/source/pobox/..."}
        }}}'
```

## 검증 / 정리

```bash
# 스크래치 DB는 런처가 생성한다(수동 CREATE 불필요). 완료 후:
docker exec kor-travel-geo-postgres psql -U addr -d kor_travel_geo_fullload_e2e -tA -c \
  "SELECT 'mv_geocode_target', count(*) FROM mv_geocode_target
   UNION ALL SELECT 'tl_juso_text', count(*) FROM tl_juso_text;"
# 같은 기준월이면 serving 기준선(각 6,416,637)과 대조.

docker exec kor-travel-geo-postgres psql -U addr -d postgres -c \
  "DROP DATABASE kor_travel_geo_fullload_e2e;"
# 검증 후 executed_job_kinds에서 full_load_batch 제거 여부는 T-290k 컷오버에서 결정.
```

serving DB(`kor_travel_geo`)는 이 절차 어디에서도 열리지 않는다 — 확인은 run 동안
`SELECT datname,count(*) FROM pg_stat_activity GROUP BY 1`에 serving DB가 없어야 한다.
