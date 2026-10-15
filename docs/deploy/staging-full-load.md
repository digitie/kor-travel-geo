# 스테이징 full-load (blue-green) 런북 — T-290j

Dagster `full_load_batch`를 **serving DB를 건드리지 않고** 격리된 스크래치 DB로 실행·검증하는
절차. serving MV(`mv_geocode_target`/`tl_juso_text`)는 열지 않는다.

> **두 절차.** 아래 본문(스크래치 DB → 검증 → 컷오버)은 **운영 중 재적재**용이다 — 보호할 serving MV가
> 있을 때. 보호할 데이터가 없는 **빈 호스트**(odroid 전환, 장애 뒤 drop → 재적재)는 맨 아래
> "빈 호스트(odroid) 풀로드 — 계획" 절을 따른다(ADR-070 proposed, 미구현).
>
> **정정(2026-10-13).** 아래 1)의 `KOR_TRAVEL_GEO_DAGSTER_EXECUTED_JOB_KINDS`는 **더는 존재하지 않는다** —
> T-290k PR3(#482) 이후 모든 실행 종류가 무조건 Dagster로 라우팅된다
> (`src/kortravelgeo/api/_full_load_launch.py:9-11` "opt-in gate … are gone"). 그 줄은 역사 기록으로만
> 남기며 설정할 것이 없다.

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
# 1) (역사 기록 — T-290k 이후 불필요) full_load_batch를 Dagster로 라우팅 (.env)
#    KOR_TRAVEL_GEO_DAGSTER_EXECUTED_JOB_KINDS=db_backup,db_restore,full_load_batch
#    → head에서는 라우팅이 무조건 Dagster(_full_load_launch.py:9-11); 설정·재배포 없음

# 2) 스테이징 full_load_batch 제출 (target_database + 파일 구동 children).
#    payload 예 (source 절대경로는 /app/data/source/... 기준):
#    (경로 정정 2026-10-13: admin 라우터는 /v1/admin 프리픽스 — src/kortravelgeo/api/app.py:177,
#     tests/unit/test_api_app_contract.py:47; 종전 예시의 /admin/loads는 오기라 404)
curl -sS -X POST http://127.0.0.1:12501/v1/admin/loads \
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
docker exec --user postgres kor-travel-shared-postgres psql -p 11000 -U shared_admin -d kor_travel_geo_fullload_e2e -tA -c \
  "SELECT 'mv_geocode_target', count(*) FROM mv_geocode_target
   UNION ALL SELECT 'tl_juso_text', count(*) FROM tl_juso_text;"
# 같은 기준월이면 serving 기준선(각 6,416,637)과 대조.

docker exec --user postgres kor-travel-shared-postgres psql -p 11000 -U shared_admin -d postgres -c \
  "DROP DATABASE kor_travel_geo_fullload_e2e;"
# (역사 기록) executed_job_kinds 게이트는 T-290k 컷오버에서 삭제됐다 — 제거할 설정이 없다.
```

serving DB(`kor_travel_geo`)는 이 절차 어디에서도 열리지 않는다 — 확인은 run 동안
`SELECT datname,count(*) FROM pg_stat_activity GROUP BY 1`에 serving DB가 없어야 한다.

## 빈 호스트(odroid) 풀로드 — 계획 (ADR-070 proposed, 미구현)

정본은 [ADR-070](../adr/070-odroid-host-and-empty-host-full-load.md) D3; 여기는 실행 순서만 둔다.
호스트 쪽 전제(odroid PG 인스턴스·NVMe fstab bind·compose v2·cgroup/memswap 효과 검사)는 Manager
ADR-58 + `prod-deployment.md`의 odroid 초기화 절(그 문서 §9.1 — 설계 §11.1에 해당)이 정본이며, 그 단계가 PASS한 뒤에만 시작한다. **2026-10-13 현재** odroid는
WSL 직접 ssh·NOPASSWD sudo·docker 그룹·NTP 수동 동기까지 완료, timesyncd 부팅 순서 drop-in·compose v2/buildx·
방화벽·fstab bind·swapfile은 미완(설계 fact base §A3).

### 전제

| 항목 | 값 | 비고 |
|---|---|---|
| 소스 위치 | odroid `/home/digitie/kor-travel-geo-data/source`(n150과 같은 경로; 실체는 fstab bind로 NVMe `/mnt/media/kor-travel/geo-data/source`) | 전국 원천 ZIP(JUSO 한글 전체분 + LOCSUM + NAVI + SHP 9 레이어 + pobox + 선택 원천)은 **n150에도 없다** — 재확보 가능 여부·용량(가정 ≤20 G)은 소유자 §14-8 |
| 소스 bind | Manager compose geo api/code-server에 **상시** `${KOR_TRAVEL_GEO_SOURCE_DIR:-/home/digitie/kor-travel-geo-data/source}:/app/data/source:ro`(Manager T-MGR-01d) | 컨테이너 경로 **`/app/data/source`가 계약**(위 payload 절대경로·overlay `docker-compose.geo-source-vol.yml:30`). 설계 §5.6·Manager T-MGR-01d 원문의 `:/source:ro`는 오기 — 그대로 구현하면 payload 파일 open 전부 실패(ADR-070 D3-2). overlay는 상시 bind 머지 뒤 불필요 |
| 프리플라이트 | `find /home/digitie/kor-travel-geo-data/source -type f \| wc -l` **> 0** ∧ `findmnt -T … -o SOURCE`가 NVMe 장치 | Docker는 없는 bind 디렉터리를 빈 채로 만들므로 "디렉터리 존재"는 검사가 아니다 |
| 라우팅 | 설정 없음(무조건 Dagster, 위 정정) | |
| run 상한 | `full_load_batch`·`load_source`·`db_restore` 24 h(`kortravelgeo_dagster/recovery.py:15,24`) | A55 ×3 가정 12 h+도 안에 든다 |
| 키 | **오늘 n150**: `ops.public_api_keys`에 Map용 발급 키 ≥1(2026-08-08 발급, 08-17 전환 완료 — `docs/journal.md:1540-1543`), VWorld 폴백 **off**, Map은 발급 키로 키 경로(actor 헤더 없음). odroid **풀로드** DB는 `public_api_keys`가 비어 VWorld 폴백만 켜지고 **Map의 현재 키는 401** → 5단계에서 odroid 로컬 admin API로 재발급(ADR-070 D2 (나) 추천) + Map `.env` 갱신 + Map 전부 재생성. **dump 복원**이면 `ops` 스키마가 dump에 들어 있어 키가 보존된다(`infra/backup.py:1175-1206`). 전환 전 기록(T-326a (2))은 "확인"이 아니라 현재 값 기록: `SELECT count(*) FROM ops.public_api_keys WHERE state = 'active'` + Map 키 200/401 | 정책은 ADR-070 D2(소유자 §14-21 — 설계의 (가) 추천은 철회, Map ADR-110 결정 §4) |
| VWorld env | odroid root `.env` `KOR_TRAVEL_GEO_VWORLD_API_KEY` **비어 있지 않음** — Manager compose 기본값이 빈 문자열(`KTG_VWORLD_API_KEY: ${KOR_TRAVEL_GEO_VWORLD_API_KEY:-}`, ktdm-t2docs `docker-compose.yml:1100,1163`)이라 odroid `.env`(신규 반입, 설계 §7.5)에서 빠지면 `public_api_key.py:144-150` 빈 집합 → `:66-67` **모든 키 거부**(발급 전 창·(가) 정책 모두) | 효과 검사: 발급 **전** `GET /v2/reverse?…&key=<VWorld 키>` 200 |

### 순서

0. **전제(설계 §11.2 8a 완료)**: geo 플립 PR 머지 → n150 재설치 → n150 geo code-server stop → odroid Manager 재설치·digest·
   validate. 효과 검사: odroid `ktdctl targets validate`에서 geo의 host == odroid(Manager ADR-58 호스트 프로필), n150 plane에
   geo code location 없음. 이 전제 없이는 odroid `ensure geo`가 geo를 자기 target으로 보지 않거나 두 호스트에 geo location이
   공존한다.
1. 소스 반입 → 프리플라이트(파일 수 > 0, NVMe 장치).
2. `ktdctl ensure geo`(odroid Manager) — api·ui·code-server 기동, `/v1/healthz` 200, Dagster code location SERVING.
3. **serving DB에 직접** `full_load_batch` 제출 — 위 curl과 같되(경로는 `POST /v1/admin/loads`, `app.py:177`)
   **`target_database`를 주지 않는다**(빈 호스트에는 보호할 MV가 없다). 소스 절대경로는 `/app/data/source/...`. run은 Dagster UI(odroid plane)에서 관찰; cancel 없이
   SUCCESS가 수용 기준. 이 한 run이 로더 → `consistency_check` → ERROR 게이트 → **`mv_refresh` child**까지 돈다
   (`src/kortravelgeo/loaders/batch_dag.py:3-4,22`, ADR-017) — 별도 mv_refresh 단계는 없고 child 소요를 소요 표에 기록한다.
4. **standalone `mv_refresh` 1회**(ADR-070 D4 입력 — batch child가 아니라 이 run의 wall clock; 상한 6 h, A55 ×3 가정 3.7~4.8 h):
   야간 schedule을 기다리거나 `POST /v1/admin/maintenance/refresh-mv`(`routers/admin.py:1867`; `/v1/admin/loads`에 `kind=mv_refresh`는
   source-load op로 가므로 쓰지 않는다)로 기동 → 소요 기록.
5. **키 정책 적용**(ADR-070 D2, URL 전환 **전** 필수): (나) 발급(추천) — odroid 로컬 admin API에서 소비자별 발급 → Map root
   `.env` `KOR_TRAVEL_MAP_KOR_TRAVEL_GEO_API_KEY` 갱신 + n150 `ensure map`(Map 컨테이너 **전부** 재생성, Map ADR-110 결정 §4(a))
   + concierge admin 설정(DB 우선) 갱신; (가) 폴백이면 DB에 키를 **발급하지 않고**(하나라도 있으면 폴백 off) Map `.env`를 VWorld
   키로 되돌려야 하는데 Map 가드(#979)가 막는다 — Map ADR-110은 채택 불가로 둔다.
6. smoke: 키 경로 `GET /v2/reverse`·`POST /v2/dataset/version` 200 — n150에서 `curl --interface 192.168.1.14
   'http://192.168.1.13:12501/v2/reverse?…&key=<Map .env 키(5단계 뒤의 발급 키)>'`(대상은 **odroid `.13`**; 전환 **전** `.14` 기록은
   ADR-070 D2·T-326a (2)). 데이터 수용 기준: batch run의 consistency report PASS + `mv_geocode_target`·`tl_juso_text` `count(*)` > 0,
   그리고 T-326a에서 미리 찍은 **n150 운영 `count(*)`**와 비교해 차이가 기준월 차이로 설명 가능(숫자 둘 다 journal). 6,416,637은
   T-061/T-290l 참고값(`docs/t055:112`, journal 2026-07-12)일 뿐 통과 조건이 아니다 — 새 원천 ZIP은 기준월이 달라 일치하지 않는다.
7. (다음 날, geo 야간 job 창 밖) 소비자 URL 전환(설계 §11.2 9단계 — Manager·HAProxy; n150 geo-api stop → `ensure map` 사이의
   짧은 창만 connect timeout). ADR-069(T-325)가 **구현돼 있으면** Track 1 센서가 새 `data_token`으로 전량 재계획을 만든다(수용,
   ADR-070 D8); 미구현이면 센서·재계획 없이 소비자가 즉시 `.13`을 본다.

### 소요 기록

| 단계 | 개발 WS(T-033) | n150 | odroid(실측 칸) |
|---|---|---|---|
| full load 전체(batch run, mv_refresh child 포함) | 4 h 08 m | serving DB 적재 없음; scratch e2e 1회(2026-07-12 T-290l, journal `:1608-1630`) — wall clock 미기록, `load_jobs`/run store에서 회수 가능하면 T-326a에 추가 | |
| 그중 SHP 적재 | 3 h 37 m | — | |
| 그중 `mv_refresh` child | — | — | |
| standalone `mv_refresh`(D4 입력) | — | 1.22~1.59 h | |
| `db_restore`(지름길 (b) 시) | — | 2.18 h(전용 12500 시절; 공용형 NOCREATEDB 롤에서는 E0410) | |
| `/v2/reverse` p50/p95 (n150→odroid, 키 경로) | — | (Map 측 Track 1 설계 추정, 저장소 밖 — 이 저장소 실측 아님) loopback 순차 p50 ≈51 min/35,754행 | |

### 지름길 — n150 dump 복원(소유자 §14-8)

n150 geo `db_backup` artifact(≈4.4 GiB, journal 2026-08-18)를 odroid에 반입해 복원. 같은 dump는 서빙 내용 지문이 같아
`data_token`이 같고 Track 1 재계획이 **0**(ADR-069 D1), `ops.public_api_keys`가 보존돼 Map의 현재 키가 그대로 유효(ADR-070 D2).
소유자 지시 "다시 로드"에 따라 기본은 풀로드.

**전제 — Dagster `db_restore`는 odroid에서 그대로 돌지 않는다.** `POST /v1/admin/restores`는 `target_dsn`이 비면
`require_db_lifecycle("db_restore")`로 CREATEDB + maintenance DB `postgres` CONNECT를 요구하고 없으면 run 생성 전에 **E0410/409**
(`src/kortravelgeo/infra/db_capabilities.py:3-11`, `routers/admin.py:2299-2310`; op 쪽 `infra/backup.py:483-489`). odroid 롤은
n150과 같은 `kor_travel_geo_app`(NOSUPERUSER/NOCREATEDB, `.env.prod.example:54`; 설계 §5.4)이라 기본 요청은 거절된다.
`target_dsn`을 줘도 serving DB에는 못 쓴다 — 대상이 현재 DB와 **달라야** 하고 비어 있어야 한다(`infra/backup.py:570-573`).
따라서 지름길은 둘 중 하나로만 실행된다(§14-8 답에 포함):

- **(a) Dagster 밖 수동 복원(추천, 롤 불변)** — odroid에서 `docker exec --user postgres kor-travel-shared-postgres pg_restore
  -p 11000 -U shared_admin -d kor_travel_geo --no-owner --no-privileges -j <n> <dump dir>` 꼴(role-neutral; 정확한 옵션은
  `build_pg_restore_command(role_neutral=True)`의 argv를 따른다, `infra/backup.py` — 실행 전 1회 대조). 빈 serving DB에
  직접이므로 hot-swap 단계 없음. 복원 뒤 `ANALYZE` + 위 순서 4~6.
- **(b) ADR-58 롤 amendment** — Manager db-init에서 geo 롤에 CREATEDB + `postgres` CONNECT 부여 → Dagster `db_restore`(새 DB,
  24 h 상한) → 수동 hot-swap(`/restores/hot-swap-plan` → `/restores/hot-swap`, `routers/admin.py:2361,2422` — `db_restore`에
  포함되지 않는 별도 단계, T-290i). 롤 설계가 바뀌므로 Manager 전달 필요(ADR-070 D3-6).

### 재적재 런북(장애 뒤, 롤백 아님)

`DROP DATABASE kor_travel_geo`(odroid 인스턴스) → db-init(Manager onboarding) → 위 1~6 → 소비자 측 확인
(Map/concierge 키 경로 200). 재적재 뒤 `public_api_keys`는 **비어 있다** — (나) 정책이면 재발급·갱신이 필수이고,
Map은 `kor_travel_geo_preflight_required`가 켜져 있으면 키 거부 시 기동이 막히므로(Map ADR-110) 재적재 창에
Map 재시작을 겹치지 않는다.
