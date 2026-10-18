# ADR-069: 데이터셋 버전에 서빙 내용 지문 기반 `data_token`을 더하고, 활성 릴리스마다 서버측 결과 캐시를 비운다

- 상태: accepted (2026-10-13 소유자 승인 — 추천안 전부: #1 C안 서빙 내용 지문, #2 fail-open(NULL =
  "판정 불가", 활성화 통과 + `notes` 접미), #18 D3 geometry 요약 지문(`ST_NPoints|Box2D`), §4a #11 활성화마다
  같은 transaction에서 `geo_cache` 전체 삭제). 구현 T-325a+b = PR #573(이 PR), T-325c 남음. 구현에서 달라진
  점은 아래 "구현 기록" 절.
- 날짜: 2026-10-13
- 결정자: 사용자 요청(2026-10-13 설계 프로그램 Track 1 "geo 주소 데이터셋 릴리스 → 소비자 반영"),
  claude 설계 + 적대 리뷰 2회(4명) + 문서 리뷰 1회(2명) 반영
- 관련: ADR-067(amend — `version_token`·`change_type`·`known_version`은 그대로 두고 필드를
  **additive**로 더한다; ADR-067 "하지 않는 것" #6 "MV 내용 해시"는 본 ADR로 뒤집는다)·
  ADR-033(ops 스키마)·ADR-036(hot-swap restore)·ADR-060(v2 additive 우선)·ADR-064(공개 키)
- 소비자 측 결정(교차 저장소, 모두 proposed): Map ADR-109(릴리스 감지 센서·지오코딩 스탬프),
  concierge ADR-49(행정코드 재해결 job). weather·transport는 geo를 호출하지 않아 **코드·계약 변경
  없음**(각 저장소 문서 1단락만 — transport T-045, weather는 task 원장 없음; 설계 §7).

## 컨텍스트

ADR-067의 `version_token`은 **릴리스 행의 함수**다 —
`"dv1-" + sha256("ktg.dataset.version:" + serving_release_id)[:32]`
(`src/kortravelgeo/core/dataset_version.py:78-88`). 따라서 데이터가 그대로인
`manual_rebuild`·MV refresh·restore에서도 토큰이 바뀌고, `change_type`은 `daily_delta`만
`delta`, 나머지 전부 `full`이다(`:91-92`). ADR-067 D1은 이것을 "허용된 과잉 감지"로 두었다.

소비자가 생기면서 그 과잉 감지가 비싸졌다. Map은 좌표 보유 활성 feature 전량(약 3.6만 행,
reverse 순차 p50 기준 약 51분 하한 — 설계 fact base 관측, 이 저장소 밖 수치)을, concierge는
전 장소를 다시 해석한다. 운영 원장에는 이미 "데이터 동일한데 토큰만 바뀐" 릴리스가 있다
(2026-08-26 `daily_delta`와 2026-09-28 `manual_rebuild`의 `source_set_hash`가 같다 — 설계
fact base의 prod 관측).

이 저장소에서 확인한 제약(2026-10-13 head `02a3c2e` 기준):

1. **`source_set_hash`는 데이터 해시가 아니다.** batch가 없는 릴리스(일변동 뒤 refresh·
   standalone 적재·manual_rebuild)의 `source_set`은 `_infer_current_source_set`이
   `load_manifest.source_yyyymm`(기준월)에서 추론한다(`src/kortravelgeo/infra/admin_repo.py:758-759`,
   본문 `:2868-2884` → `source_yyyymm_by_kind` `:2802`). 일변동은 기준월을 바꾸지 않으므로 법정동
   폐지(MVM 63/64)가 들어와도 해시가 그대로다(세 분기 — batch source_set → consistency report
   source_set → 추론, `:754-759` — 중 **추론 분기에서만** 성립; CLI `daily-juso`는 batch 없이
   `release_kind="daily_delta"`로 부른다, `cli/main.py:304-312`). `mv_hash`도 `md5(viewdef ‖ row_count)`라
   내용 해시가 아니다(`admin_repo.py:2921-2944`).
2. **v2 응답을 만드는 표는 MV 둘만이 아니다.** reverse는 `mv_geocode_target` + `tl_sppn_makarea`
   (`infra/reverse_repo.py:80-99`), 우편번호는 `mv_geocode_target` → `postal_bulk_delivery` →
   `tl_kodis_bas`(`infra/zip_repo.py:16-54`), geometry/도로는 `tl_spbd_buld_polygon`·`tl_sprd_manage`·
   `tl_scco_{ctprvn,sig,emd,li}`·`region_radius_parts`(`infra/geometry_repo.py:30-40, 85-111`),
   search는 MV 둘 + `tl_scco_*`(`infra/search_repo.py`).
3. **릴리스를 만드는 네 경로가 한 헬퍼를 지난다.** `record_mv_refresh_release`(`admin_repo.py:723`,
   호출 `:789`)·`record_restore_candidate`(`:952`, 호출 `:995`)·`record_hot_swap_release`(`:1057`,
   호출 `:1077`)·`record_hot_swap_rollback_release`(`:1104`, 호출 `:1123`)는 전부
   `_insert_dataset_snapshot_and_release`(`:3003`)를 부르고, 이 헬퍼는 `release_state == 'active'`면
   `mv_hash`를 내부에서 fallback 계산한다(`:3165-3167`). `conn`은 이미 쓰기 대상 DB를 가리킨다
   (`:3026-3041` 주석). 헬퍼는 진입 직후 transaction-scoped
   `pg_advisory_xact_lock(SERVING_RELEASE_ACTIVATION)`을 잡고 끝까지 보유한다(`:3042-3049`) — 이
   lock은 원장 read-decide-write만 직렬화하고 데이터 적재는 직렬화하지 않는다.
4. **서버측 결과 캐시 `geo_cache`(geocode·reverse)가 릴리스를 모른다.** 기본 켜짐·TTL 30일
   (`settings.py:97-98`). reverse는 키 `x,y,crs,type,zipcode,simple,radius_m,sig_cd,bjd_cd`뿐
   (`client.py:592-611`), hit면 core를 거치지 않고 반환한다(`client.py:549-553`); geocode도 같은 표에
   `service="geocode"`로 저장·조회한다(`client.py:494-505` get, `:613-629` set). 비우는 곳은
   `refresh_mv`의 `loaders/postload.py:67, 95` 두 곳뿐이다. 그런데 standalone direct-serving
   적재(sppn_makarea/pobox/bulk/epost/shp)는 `refresh_mv` 없이 `record_mv_refresh_release`만 호출해
   릴리스를 만든다(Dagster `loaders/batch_dag.py:428-430, 470-480`; CLI `cli/main.py:507(shp),
   548(shp-all), 580(sppn-makarea), 603(pobox), 626(bulk), 688(epost)` 여섯 곳). 즉 토큰은 바뀌는데
   reverse 답은 옛 우편번호·옛 SPPN 후보이고, `tl_sppn_makarea`를 읽는 geocode(`infra/geocode_repo.py`)
   hit도 옛 후보다 — 소비자가 "값 동일"로 읽고 새 토큰으로 봉인하는 **거짓 음성**이 두 경로의
   캐시에서 재현된다.
5. **응답에 버전이 없다.** `GeocodeV2Response`(`dto/v2.py:156`)·`ReverseV2Response`(`:193`)·
   `SearchV2Response`(`:223`)·`RegionsWithinRadiusResponse`(`:279`) 어디에도 데이터셋 버전
   필드가 없어, 배치 도중 릴리스가 활성화되면 어느 행이 어느 데이터로 해석됐는지 알 수 없다.
   reverse `metadata`는 비안정 필드다(`core/v2.py:253-258`).
6. 알림 자리 후보 `ops.run_failure_alerts`는 run 단위 표다(`run_id TEXT PRIMARY KEY`,
   `run_failed_at NOT NULL`, `infra/sql.py:480-492`) — CLI/restore 경로의 실패를 넣을 run이 없다.
   `serving_releases.notes TEXT`는 있다(`sql.py:570`). dto는 core를 import하지 못해 토큰 패턴을
   중복 선언한다(`dto/v2.py:290-292`). ops DDL은 `infra/sql.py` + `sql/ddl/001_schema.sql` +
   Alembic 세 곳이 함께 정본이다.
7. **OpenAPI는 PR마다 검사된다.** `.github/workflows/openapi.yml`(`on: pull_request`)이
   `scripts/export_openapi.py --check --output openapi.json`을 돌리고(`:21`), `ci.yml:135-137`은
   UI `npm run gen:types` 뒤 `types/api.gen.ts`·`lib/schemas.gen.ts`의 diff 0을 요구한다
   (`kor-travel-geo-ui/scripts/gen-types.mjs:15`가 루트 `openapi.json`을 읽는다). 따라서 DTO를
   바꾸는 PR은 `openapi.json`과 생성 파일을 같은 PR에 실어야 CI green이 된다.

## 결정

**활성 릴리스마다 "소비자가 실제로 읽는 표"의 내용 지문을 계산해 `data_token`으로 공개하고,
같은 transaction에서 `geo_cache`를 비우며, 네 v2 응답에 `dataset{version_token, data_token}`을
싣는다. 소비자는 `data_token` 동등성으로만 "바뀌었는가"를 판정한다.**

### D1 — `data_token`은 서빙 내용 지문에서 파생한다

```
data_fingerprint = md5(string_agg(t || ':' || coalesce(h, 0)::text, ',' ORDER BY t))   -- 32 hex, 표마다 h = sum(hashtextextended(행 직렬화, 0)::numeric)
data_token       = "dd1-" + sha256(data_fingerprint)[:32]
```

- 저장: `ops.dataset_snapshots.data_fingerprint TEXT NULL` — Alembic `0029_t325a_data_fingerprint`(원안 이름은 32자 초과 — 구현 기록 4)
  (저장소 관례 `NNNN_tNNN_slug`; 직전 head `0028_t319_source_month_manifest`) + `infra/sql.py:522-545`
  DDL + `sql/ddl/001_schema.sql:485` 사본(세 곳 동기).
- 파생: `core/dataset_version.py`에 `DATA_TOKEN_PREFIX = "dd1-"`, `DATA_TOKEN_RE = ^dd1-[0-9a-f]{32}$`,
  `derive_data_token(fingerprint) -> str`. 지문 NULL이면 `data_token = None`(응답에서 생략).
- `sum(numeric)`은 순서 무관·중복 안전·오버플로 없음. `to_jsonb(row)` 직렬화라 MV 열이 추가돼도
  지문이 따라온다(열 추가 = 토큰 변경 1회, 허용). 빈 표는 `coalesce(h, 0)`으로 안정.
- trade-off: `to_jsonb(row) - 'pt_5179' - 'pt_4326'`은 geometry 두 열을 **먼저 GeoJSON으로 직렬화한
  뒤 버리므로** 642만 행에서 비용이 크다. 실측(D9)이 기준을 넘으면 지문 열을 명시 선택하는 것이
  첫 지렛대다 — 그 경우 "열 추가 자동 추종"은 포기하고 lint(D2)가 열 목록까지 고정한다.

### D2 — 지문 표 집합은 손으로 고르지 않고 유도한다

정의: **"v2 응답을 만드는 infra repo(`reverse_repo`·`zip_repo`·`geometry_repo`·`geocode_repo`·
`search_repo`)의 SQL이 `FROM`/`JOIN`하는 표 집합"**. 2026-10-13 head에서 유도한 집합(11표 — 1차 리뷰 뒤 v1 전용 두 표를 빼 9표, 구현 기록 12):

| 표 | 읽는 repo | 지문에 넣는 열 |
|---|---|---|
| `mv_geocode_target` | reverse·zip·geocode·search | 비-geometry 전 열 + `md5(ST_AsBinary(pt_5179))`. `pt_4326`은 `ST_Transform` 산출(`sql.py:1410-1415`)이라 PROJ/PostGIS 업그레이드만으로 바뀌므로 **제외** |
| `tl_scco_ctprvn`·`tl_scco_sig`·`tl_scco_emd`·`tl_scco_li` | geometry·search | `(code, name, geom 요약)` — `ctprvn_cd/ctp_kor_nm`·`sig_cd/sig_kor_nm`·`emd_cd/emd_kor_nm`·`li_cd/li_kor_nm`(`sql.py:199-233`) |
| `region_radius_parts` | geometry(within-radius) | 비-geometry 전 열 + geom 요약(`sql.py:235-245`; `refreshed_at` 제외) |
| `tl_kodis_bas` | zip | `bas_mgt_sn, bas_id` + geom 요약(`sql.py:247-254`) |
| `postal_bulk_delivery` | zip | `zip_no, bd_mgt_sn, bulk_name, detail`(`sql.py:360-367`; geometry 없음, `bulk_id BIGSERIAL`은 아래 규칙으로 제외) |
| `tl_sppn_makarea` | reverse·geocode | 전 열 + geom 요약 |
| `tl_spbd_buld_polygon`·`tl_sprd_manage` | geometry | 전 열 + geom 요약 |

- 공통 제외 열: (a) `source_file`·`source_yyyymm`·`loaded_at`·`refreshed_at` 같은 적재 메타, (b)
  적재마다 다시 부여되는 **surrogate key**(`SERIAL`/`BIGSERIAL`/IDENTITY — 현재 집합에서는
  `postal_bulk_delivery.bulk_id`). 둘 다 데이터가 같아도 재적재마다 바뀌므로 넣으면 재빌드를
  걸러내지 못한다(`sum()` 설계라 행 정렬에 의존하지 않으므로 빼도 안전).
- 허용 목록(유도 집합에 **실제로 있으나** 지문에서 빼는 표, 사유를 lint에 적는다):
  `mv_geocode_text_search`(geocode·search가 읽음; 같은 원천에서 같은 REFRESH로 파생, 정의 변경은
  코드 릴리스) 하나.
- `geo_cache`는 다섯 repo가 읽지 않는다(`GeoCacheRepository`를 `client.py`가 읽는 client 계층의
  파생 캐시) — 유도 집합 **밖**이며 D6에서 무효화한다. 허용 목록에 넣지 않는다(본 적 없는 항목을
  허용 목록에 두면 아래 (3)의 실재 검사가 빨갛게 된다).
- `postal_pobox`는 다섯 repo가 읽지 않는다(`pobox_repo.py`는 v1 `/v1/address/pobox`
  전용, `api/routers/pobox.py:17`). T-325a에서 최종 확인해 v2 경로가 읽으면 집합에 넣는다.
- `_ROW_COUNT_OBJECTS`(`admin_repo.py:205-216`)는 원천 표 목록이라 이 집합의 출처로 쓰지 않는다.
- lint `tests/unit/test_data_fingerprint_covers_serving_tables.py` — 유도 절차를 고정한다:
  (1) 다섯 repo 모듈 **소스 문자열 전체**(주석·docstring 포함)에서 `\b(FROM|JOIN)\s+([a-z_][a-z0-9_]*)`
  식별자 집합을 뽑는다 — **대소문자 구분**(`re.IGNORECASE` 금지): head의 SQL 키워드는 전부 대문자이고
  Python `from __future__`·`from kortravelgeo…`는 소문자라 그래서만 제외된다. 소문자 SQL 키워드(`from
  tl_x`)는 lint가 못 보므로 대문자 규약은 ruff/리뷰로 지킨다. 열 선택 규칙(위 제외 열)은 SQL 상수
  쪽 규칙이라 lint 초록이 열까지 보증하지는 않는다.
  (2) 같은 모듈에서 `\b([a-z_][a-z0-9_]*)\s+AS\s+(?:(?:NOT\s+)?MATERIALIZED\s+)?\(`로 잡히는 **CTE 이름**
  (head 기준 `target_pt`·`query_input`·`ranked`·`sig_regions` 등과 `AS MATERIALIZED (` 변형
  `knn_candidates`(`reverse_repo.py:22`)·`candidates`(`geocode_repo.py:120`)·`exact_keys`·`scored`
  (`search_repo.py:18, 74`) — MATERIALIZED를 안 잡으면 이 넷이 (1)에 남아 즉시 빨갛다)과 식별자 바로
  뒤에 `(`가 오는 **함수 호출**(`generate_series` 등)을 뺀 뒤,
  (3) 허용 목록의 각 항목이 (2)의 결과에 **실제로 존재**하고, `(2) − 허용 목록 == DATA_FINGERPRINT_TABLES`
  (양방향 등식, 비어 있지 않음 — 빈 집합·항진명제 방지)여야 한다. 새 표를 읽기 시작하거나 집합에서
  빠지거나 허용 목록에 유령 항목이 들어가면 빨갛게 된다. 효과 검증은 T-325a 수용 기준의 "일부러
  빨갛게"(가짜 `JOIN tl_new_table` 추가 → 실패; 허용 목록에 없는 표 이름 추가 → 실패; MATERIALIZED CTE만
  추가 → 통과).

### D3 — geometry는 비용 등급을 나눈다(점은 정확, 폴리곤·선은 요약)

- 점(`mv_geocode_target.pt_5179`): `md5(ST_AsBinary(pt))`.
- 폴리곤·선(`tl_scco_*`·`region_radius_parts`·`tl_sppn_makarea`·`tl_spbd_buld_polygon`·
  `tl_sprd_manage`·`tl_kodis_bas`의 geometry): 전체 WKB를 직렬화하지 않고
  `concat(ST_NPoints(geom), '|', Box2D(geom)::text)` **요약**만 센다.
- **명시된 한계(가정·트레이드오프).** 정점 수와 bbox가 그대로인 미세 경계 이동(좌표 재투영·
  단순화·정밀도 변경)은 토큰을 바꾸지 않는다 — within-radius 가장자리 판정이 바뀌는 경우를
  놓칠 수 있다. 소비자가 읽는 값은 코드·명칭·우편번호·반경 포함 여부·최근접 건물이지 정점
  정밀도가 아니라는 판단이고, 건물 폴리곤 수백만 행의 WKB md5는 n150 디스크 대기에서 10분을
  넘겨 D5의 fail-open이 상시 발동할 위험이 크다(그러면 재빌드 최적화가 prod에서 한 번도
  작동하지 않는다). 소유자 승인 대기(설계 §12 #18, 후속 참조).

### D4 — 계산 위치는 공유 헬퍼 한 곳이다

`_insert_dataset_snapshot_and_release` 안에서, `mv_hash`와 **같은 규칙**(`admin_repo.py:3165-3167`)으로:
호출자 인자 `data_fingerprint=`가 `None`이고 `release_state == 'active'`이면 지문을 계산하고, 인자가
있으면 그 값을 저장한다(테스트 전용). `DELETE FROM geo_cache`(D6)는 인자와 **무관하게** active면 항상
실행한다. 이러면 mv_refresh·restore·hot-swap·rollback 네 경로가 한 번에 덮이고
`hotswap.py`·`partial_restore.py`·`postload.py`는 손대지 않는다.

**위치는 advisory lock 획득 전이다.** 지문 SELECT는 같은 transaction 안이되
`pg_advisory_xact_lock(SERVING_RELEASE_ACTIVATION)`(`:3042-3049`) **앞**에서(savepoint 안, D5) 실행한다.
lock은 원장 read-decide-write만 직렬화하고 데이터 적재는 직렬화하지 않으므로 지문 결과는 lock 안에서
계산한 것과 같고, lock 보유 시간은 지문 시간(≤10 min, 2026-10-18부터 ≤30 min)만큼 늘지 않는다 — 동시 활성화 호출자
(restore·hot-swap·rollback은 `statement_timeout=0`이라 무기한, admin API 경로는 기본 timeout으로
lock 대기 중 실패)가 지문을 기다리는 일이 없다. `DELETE FROM geo_cache`는 쓰기이므로 lock 뒤 원장
INSERT와 같은 자리에서 실행한다.
`_dataset_version_candidate`/`_dataset_version_entry`에 `data_token`을 투영하고,
`current_dataset_ref()`(`WHERE state='active'` 1행, `admin_repo.py:816-818`과 같은 SELECT)가
`(version_token, data_token)`만 돌려준다.

### D5 — 지문은 fail-open이고 알림은 `serving_releases.notes` 한 자리다

- 지문 쿼리는 **savepoint 안에서** `SET LOCAL statement_timeout = '10min'`(2026-10-18 소유자 결정으로 `'30min'` — odroid 조용한 실측 240 s)을 따로 걸고,
  실패·timeout이면 `data_fingerprint = NULL`로 활성화를 **통과**시킨다. 지문 SELECT가 끝나면
  성공·실패 모두 **`ROLLBACK TO SAVEPOINT`**로 닫는다(읽기 전용이라 잃는 것이 없고, `SET LOCAL`은
  savepoint를 RELEASE하면 transaction 끝까지 남지만 ROLLBACK TO면 되돌아간다). 그래서 각 경로의
  기존 `statement_timeout`(mv_refresh 30min `admin_repo.py:748`(현재 `record_mv_refresh_release` 첫 SET) — 2026-10-18 ADR-068 개정으로 6h, restore/hot-swap/rollback `0`
  `:994, :1076, :1122`)이 지문 뒤 INSERT·`DELETE FROM geo_cache`(D6)에도 그대로 적용된다.
  대안 "지문 실패 = 활성화 실패"는 restore까지 막으므로 기각.
- **fail-open의 대가.** 지문 없는 활성 릴리스에서 소비자는 "바뀜"으로 재처리하는 것이 아니라
  **판정 불가로 멈춘다**(D8). 즉 fail-open이 활성화를 통과시키는 값은 "과잉 재처리"가 아니라
  "backfill(D9)이나 다음 활성화까지 소비자 정지"다. 그 정지를 보이게 하는 것이 아래 `notes`
  접미·UI 배지·배너이고, 복구 수단이 D9의 CLI다. (설계 초안 §4a #5는 "NULL = 바뀜(안전 방향)"
  이었으나 2차 리뷰 R4-4에서 소비자 규약이 "판정 불가"로 바뀌어 근거를 이렇게 고쳐 적는다 —
  소유자 승인 항목 §12 #2에 이 의미 변경을 포함한다.)
- 알림: 새 열·새 표 없이 `serving_releases.notes`에 접미
  `data_fingerprint_failed: <error_code>`(`error_code ∈ timeout | schema_drift:<table> |
  superseded_during_scan | schema_missing | exception:<ClassName>` — 뒤 셋은 구현 기록 9·13·14)를 같은
  INSERT에 싣는다(헬퍼는 `notes` 인자를 이미 받아 `serving_releases` INSERT에 바인딩한다, `:3022, :3172`).
  `ops.run_failure_alerts`는 run 단위 표라 쓰지 않는다(컨텍스트 6).
- 노출: `GET /v1/admin/ops/releases`의 `ServingRelease.notes`(기존 필드) + `data_token` NULL →
  UI "지문 없음" 배지, 툴팁에 접미. **승격 규칙**: 연속 두 활성 릴리스가 지문 없음이면
  `/admin/ops` 상단 경고 배너(UI 계산, 서버 변경 없음).

### D6 — 활성 릴리스마다 같은 transaction에서 `geo_cache`(geocode·reverse)를 비운다

`_insert_dataset_snapshot_and_release`에서 `release_state == 'active'`이면 **지문 계산과 같은
`conn` transaction에서**(lock 뒤, D4) `DELETE FROM geo_cache`를 실행한다(네 경로 공통; 표 전체 —
geocode 행과 reverse 행을 가리지 않는다). `GeoCacheRepository`는 `AsyncEngine`을 받아 `clear()`가
자기 transaction을 열므로(`infra/cache.py:29-30, 84-87`) 그대로 못 쓴다 —
`GeoCacheRepository.clear_on(conn)`을 추가하고 SQL 상수 `_CLEAR_SQL` 하나를 `clear()`와 공유한다
(단일 정본). `postload.py`의 기존 clear 두 곳은 그대로 둔다(중복 삭제 무해). 이 결정은 2차 리뷰
R3-1(HIGH) 반영으로 설계에서 확정했으나 prod 가시 비용(활성화 직후 첫 reverse·geocode p50 일시
상승)이 있어 **설계 plan의 owner_decisions에 §4a #11로 올라 있다** — 소유자가 §12 #1·#2·#18과
함께 확인한다(후속).

기각한 대안: 캐시 키 네임스페이스에 토큰을 접두 — TTL 30일 동안 옛 키가 쌓이고, D7의 "캐시
hit에도 현재 토큰" 규칙과 어긋난다.

### D7 — 네 v2 응답 최상위에 `dataset: {version_token, data_token}`을 싣는다

- `dto/v2.py`에 `DatasetRef(FrozenModel){version_token: str, data_token: str | None}`(패턴은
  dto에 중복 선언 — core import 불가). 네 응답 클래스에 `dataset: DatasetRef | None = None`.
- 채우는 곳: `api/dataset_ref.py`의 의존성 `get_dataset_ref()`(응답 조립용 **프로세스 캐시**, TTL
  10 s, 시간 주입 가능 — reverse 결과 캐시 `geo_cache`와 별개) → `AdminRepository.current_dataset_ref()`.
  핸들러 네 곳(`api/routers/v2.py:35-124`)은 core가 돌려준 frozen 인스턴스를
  `model_copy(update={"dataset": ref})`로 끼운다. active 릴리스가 없으면 `None` → 이미 켜진
  `response_model_exclude_none=True`가 생략한다.
- `geo_cache`에는 토큰을 넣지 않고 응답 조립 시 붙인다 → **캐시 hit에도 현재 토큰**. 이 규칙이
  옳으려면 D6이 필요하다(활성화 commit 직후 in-flight 요청의 재삽입 창은 결과(부정) 참조). 외부
  출처(`candidates[].source ∈ {vworld, juso}`, `dto/v2.py:25`; `client.py:506-509` fallback →
  `infra/external_api.py:36-45`가 VWorld 키 없으면 juso) 후보가 섞인 응답에서도 `dataset`은 **로컬
  데이터셋**의 버전이다 — 소비자는 `candidates[].source`로 외부 출처를 구별한다.
- 10 s 창 동안 옛 토큰이 실릴 수 있다 — 소비자는 "옛 토큰 = 다시 한다" 방향이라 안전.
- 기각한 대안: (1) 미포함(배치 전후 `/v2/dataset/version`만) — 배치 도중 활성화 시 행별 판단
  불가; (2) 응답 헤더 — Map 클라이언트(`map:src/kortravelmap/geocoding.py` `reverse()`, JSON 본문만
  파싱)와 Map admin geo proxy(`map:packages/kor-travel-map-admin/frontend/src/app/api/geo/[...path]/route.ts`,
  본문 전달)가 헤더를 버린다(Map origin/main `c4d17343e`에서 확인; 정본은 Map ADR-109).

### D8 — 소비자 규약은 "`data_token` 동등성, 없으면 판정 불가, `version_token`은 관측용"이다

- `DatasetVersionEntry`(`dto/v2.py:295`)에 `data_token: str | None` 추가(지문 NULL 릴리스는
  필드 생략). `version_token`·`change_type`·`DatasetVersionInput.known_version`(릴리스 토큰)은
  **그대로**(호환). `data_changed` 같은 편의 필드는 두지 않는다 — 소비자가 문자열을 비교한다.
- 소비자는 `current.data_token`을 저장·비교한다. 같으면 재빌드(무동작), 다르면 전량 재해석,
  **없으면 판정 불가** — Map 센서는 계획을 만들지 않고 빨간 Skip 사유를 남기고, concierge는
  종료한다(각 ADR). 그래서 지문 없는 활성 릴리스는 backfill 전 과도기와 지문 실패 시에만
  존재한다.
- **문구 통일(교차 저장소).** 설계 초안 §4a #5/#10·§4d·§8은 "없으면 바뀜"이었고, 2차 리뷰
  R4-4 반영(§5.4 #1·§9·§12 #9)으로 "판정 불가(계획 없음)"로 통일했다. 이 규약은 geo 문서가
  정본이며(설계 §8 C안) **Map ADR-109·concierge ADR-49도 같은 문구를 써야 한다** — "없으면
  바뀜"을 옮긴 소비자 문서는 틀린 것이다.
- **amendment(2026-10-15, 소유자)** — **기준선 규칙(2026-10-15 소유자 결정)**: 소비자가 저장한 `data_token`이 **없는** 상태(한 번도 관측하지 못함 — 예: n150 geo는 Alembic 0028이라 토큰이 없었다)에서 처음 토큰을 받으면 그것은 **기준선(baseline)으로 저장만 하고 재해석·재계획하지 않는다**. 재해석은 저장된 토큰과 새 토큰이 **둘 다 있고 다를 때만**이다(열 제약 odroid에 전량 재지오코딩 폭주 방지). 동기: ADR-070 실행 기록 8. Map ADR-109·concierge ADR-49 구현이 같은 규칙을 따른다.
- 활성화 알림은 소비자 센서의 `POST /v2/dataset/version` 폴링이다 — geo가 소비자를 알거나
  webhook을 내는 안(의존 방향 역행, ADR-067 비목표 #3)과 공용 Dagster run storage에서 geo run을
  관찰하는 안(CLI·restore 경로를 못 본다)은 기각.
- 릴리스 간 코드 단위 diff(`POST /v2/dataset/changes`)는 이번 계약에 넣지 않는다 — 명칭 변경·
  좌표 이동·우편번호 변경은 코드 diff로 못 보며, 범위를 좁히면 "놓치고 끝났다고 믿는" 거짓
  안심이 생긴다. phase 2 후보(후속).

### D9 — 기존 활성 릴리스는 CLI로 1건만 backfill한다(읽기 전용 실측 모드 포함)

`ktgctl serving fingerprint-active`(`cli/main.py` `serving_app` 하위): 활성 릴리스 1건의
`data_fingerprint`를 계산·저장하고 `DELETE FROM geo_cache`를 함께 실행한다(backfill은 헬퍼를
지나지 않으므로 명시 실행). 이력 행은 NULL로 둔다.

- `--dry-run`: 저장·캐시 삭제 없이 지문 SQL만 실행해 **경과 시간과 표별 `h` 값**을 출력한다
  (읽기 전용). 헬퍼와 **같은 `DATA_FINGERPRINT_SQL` 상수를 같은 `SET LOCAL statement_timeout`(`DATA_FINGERPRINT_STATEMENT_TIMEOUT`, 2026-10-18부터 `'30min'`)
  안에서** 실행한다 — 측정 대상 = 수용 기준 대상. T-325a 수용 기준 "prod 규모 사전 실측"의 수단이다
  — 소유자가 PR-1 브랜치 체크아웃의 `ktgctl … --dry-run`으로 n150 prod DB에 **머지 전** 1회
  실행한다(미머지 코드로 prod를 **쓰지 않는다**).
- admin `ServingRelease`(`dto/admin.py:756`)에 `data_token` additive 필드, OpsPanel releases
  표(`components/admin/OpsPanel.tsx:104-126`)에 열·배지,
  `components/admin/ops/DatasetVersionDetailDialog.tsx` live preview에 `data_token`.

## 근거

| 안 | 내용 | 판정 |
|---|---|---|
| A. 현행 유지 + `change_type`에 `rebuild` 추가 | `manual_rebuild`/`restore`면 `rebuild` | 기각 — restore가 다른 데이터를 가져올 수 있고 refresh도 delta 적용 뒤면 데이터가 바뀐다. 종류로 데이터 동등성을 **추정**하는 것이라 틀린다 |
| B. `data_token = "dd1-" + source_set_hash[:32]` | 이미 있는 열, 비용 0 | 기각 — 일변동을 못 본다(컨텍스트 1). 독립 재검토가 택했다가 prod 해시 동일 관측으로 철회 |
| **C. 서빙 내용 지문(채택)** | 활성화 시점에 v2 응답 표의 내용 해시 | 소비자가 실제로 읽는 것의 함수. 일변동·보조 표 단독 적재·재빌드·restore·rollback 전부 옳게 판정. 비용은 활성화당 스캔 1회 + 열 1개 |

- 정확성(거짓 음성 불허, ADR-067 근거 1)이 첫째다 — 지문이 일변동·보조 표를 놓치면 "바뀌었는데
  안 바뀐 척"이 되어 재빌드 최적화의 역방향 거짓 안심이 생긴다. 그래서 표 집합은 "원천 파일
  집합"이 아니라 "응답을 만드는 모든 표"이고, 손으로 고르지 않고 유도·lint한다(D2).
- 단일 정본: 토큰 하나(`data_token`)로 소비자 셋이 같은 판정을 한다. 네 경로를 헬퍼 한 곳에서
  덮는다(D4). 캐시 SQL 상수 하나(D6).
- 단순성: 편의 필드·새 표·새 알림 경로·webhook 없음. 기존 필드는 전부 그대로.
- 복원 내성: 지문은 DB 내용의 함수라 hot-swap restore가 원장을 되돌려도 옳다 — 소비자는
  동등성만 보므로 이력 소실에 영향받지 않는다.

## 결과(긍정)

- 데이터 동일 재빌드·restore·rollback에서 소비자 전량 재처리가 사라진다(토큰 불변).
- 일변동·우편번호·SPPN·건물 폴리곤 단독 적재가 토큰에 반영된다.
- standalone 적재 뒤 옛 답이 30일 동안 캐시에 남던 문제가 닫힌다(D6).
- 배치 도중 릴리스가 활성화돼도 행별로 어느 데이터로 해석됐는지 알 수 있다(D7).
- 기존 계약(`version_token`·`change_type`·`known_version`·`history`)은 변경 없음, 전부 additive(ADR-060).

## 결과(부정)

- 활성화 작업에 약 642만 행(`mv_geocode_target`, T-290l 기준 6,416,637행) + 보조 표 스캔 1회가
  더해진다. n150은 디스크 대기가 병목이라 "수십 초"는 추정일 뿐이다 — **prod 규모 사전 실측
  1회**(D9 `--dry-run`, `/proc/pressure/io` 동시 기록)가 T-325a 수용 기준이며, 10 min timeout의
  50%(5 min)를 넘으면 머지 전 설계 재검토 — 지렛대 순서: `to_jsonb(row)` 대신 지문 열 명시 선택
  (열 추가 자동 추종 포기, D1) → 표 집합 축소·요약 강화·`mv_geocode_target` 열 축소.
- 지문 실패 시 소비자는 판정 불가로 멈춘다(계획 없음) — `notes` 접미와 UI 배지·배너로 추적,
  복구는 D9 CLI.
- 활성 릴리스 직후 첫 reverse·geocode p50이 일시 상승한다(D6 캐시 전부 삭제).
- ~~활성화 commit 직후, 옛 데이터로 계산을 끝낸 in-flight 요청이 `set_json`(`client.py:505, :560`)으로
  옛 답을 재삽입할 수 있는 창(요청 1건 길이)은 **알고 받아들인다**~~ — **구현 기록 10이 대체**(캐시 키에 release를 넣어
  닫았다). 원래 문장: — 닫으려면 캐시 행에
  `serving_release_id`를 함께 저장하고 hit 시 비교해야 한다(후속 후보, 이번 범위 밖). "`geo_cache`
  0행" 수용 기준은 순간 상태라 이 창을 보지 않는다.
- 지문 SELECT는 lock 앞이라(D4) 활성화 lock 보유 시간은 늘지 않지만, 활성화 transaction 자체의
  길이는 지문 시간만큼 늘어난다.
- D3 요약 지문은 정점 수·bbox가 같은 미세 경계 이동을 놓친다.
- MV 열 추가 등 스키마 변경은 데이터가 같아도 토큰을 1회 바꾼다(허용).
- 세 곳 DDL 정본 관행에 열 1개가 더해진다.

## 구현 기록 (T-325a+b, PR #573, 2026-10-13)

결정은 그대로이고, 구현하면서 다음이 정해지거나 달라졌다.

1. **D1 지렛대 1을 머지 전에 썼다 — 지문 열은 명시 목록이다.** 첫 prod dry-run(설계대로 `to_jsonb(row) - …`)이
   10 min timeout에 걸렸다(600 s, fail-open으로 `error_code=timeout` — 경로 자체는 의도대로 동작). 폴리곤을 GeoJSON으로
   직렬화한 뒤 버리는 비용이 원인이라 D1이 적은 첫 지렛대(열 명시)로 바꿨다: 행 입력은
   `ROW(열…)::text || '|' || md5(ST_AsBinary(pt_5179)) || '|' || concat(ST_NPoints(geom), '|', Box2D(geom)::text)`.
   대가도 D1이 적은 그대로 — 열 추가 자동 추종은 없고, lint가 열 목록까지 고정한다(`infra/data_fingerprint.py`의
   `FingerprintTable.columns`; 단위 lint는 `infra/sql.py` DDL·MV select 목록을, 통합 테스트는 live `pg_attribute`를
   `columns ∪ point ∪ summary ∪ dropped = 실제 열 − EXCLUDED_COLUMNS`로 대조).
2. **prod 규모 실측(n150, 2026-10-13, 읽기 전용 `--dry-run`, 배포 이미지 + PR 브랜치 소스).** 대상 11표 heap+toast
   약 6.98 GB(`tl_spbd_buld_polygon` 3.57 GB·약 1,070만 행, `mv_geocode_target` 1.89 GB·6,417,026행, 나머지 < 0.6 GB).

   | 회 | SQL | 결과 | 비고 |
   |---|---|---|---|
   | 1 | `to_jsonb` (설계 원안) | **timeout 600 s** → fail-open | PG 3코어 근처 사용 |
   | 2 | 명시 열 | 204 s에 `exception:OutOfMemory`(SQLSTATE 53200 "out of shared memory") → fail-open | 아래 3. 직전 1회 직후·load 10~12·IO pressure some 60~95% |
   | 3 | 명시 열 | **57.4 s** 성공 | 2회 직후라 page cache warm |
   | 4 | 명시 열 | **103.4 s** 성공 | 시작 시 대상 파일의 page cache 상주 15%(`fincore`); 지문이 3회와 같음(결정성) |

   판정: 성공 측정은 10 min timeout의 50%(300 s) 안이다(최대 103 s = 17%). 단, 2회처럼 디스크 경합이 큰 때는
   204 s를 넘겼다(끝나기 전 중단) — 활성화 시점의 부하에 따라 수 분이 될 수 있다. 넘으면 fail-open이고 복구는 D9 CLI다.
3. **운영 관측(이 저장소 밖 문제).** 공용 PG(`kor-travel-shared-postgres`)에서 Map의 `feature-write` advisory lock
   (`pg_advisory_xact_lock(hashtextextended('feature-write:' || …))`)이 lock table을 채워 2026-10-12 09Z부터 시간당 약
   120건 `out of shared memory`(HINT `max_locks_per_transaction`)가 난다. 같은 instance의 다른 DB(geo 포함)의 새 lock
   획득도 그 순간 실패한다 — 2회 실측이 그렇게 죽었다. 지속되면 geo 활성화의 지문도 가끔 fail-open이 된다. Map/Manager에
   전달할 사항.
4. **Alembic revision id는 `0029_t325a_data_fingerprint`다**(D1이 적은 `0029_t325a_dataset_data_fingerprint`는 35자라
   `alembic_version.version_num varchar(32)`를 넘는다 — 기존 `test_alembic_revision_ids_fit_default_version_table`).
5. **캐시 무효화 수용 기준의 reverse 케이스는 `tl_sppn_makarea`로 했다.** reverse 응답의 우편번호는
   `mv_geocode_target.zip_no`(`core/reverse_geocoder.py`)이고 `postal_bulk_delivery`는 `zip_repo`(우편번호 조회)만 읽는다 —
   T-325a 수용 기준 문구("reverse … `postal_bulk_delivery` 1행 변경 → 새 우편번호")는 reverse로는 재현할 수 없다.
   reverse는 SPPN 구역(`tl_sppn_makarea`)을 읽으므로 그 표로 같은 효과(standalone 릴리스 뒤 새 구역명·새 `data_token`)를
   단언했고, `postal_bulk_delivery`는 지문 민감도·재적재 동일성 테스트가 맡는다. geocode는 v2 응답이 SPPN 구역명을
   싣지 않아 v1·v2가 공유하는 geocode 결과 캐시층에서 구역명을, v2 응답에서 `dataset`을 따로 단언했다.
6. **backfill(D9, `--dry-run` 없이)은 스캔 뒤 activation advisory lock을 잡고 활성 snapshot이 그대로인지 확인한 다음에만
   쓴다** — 스캔 도중 새 활성화가 있었으면 쓰지 않고 실패한다(재실행). `--dry-run`은 `SET TRANSACTION READ ONLY` 안에서 돈다.
7. (구현 기록 10·16이 대체 — 스탬프는 이제 클라이언트가 읽고, 실패는 1초 캐시한다.) **`dataset` 조립 실패는 필드 생략이다.** `get_dataset_ref`가 원장 조회에 실패하면 경고 로그만 남기고 `dataset`을
   생략한다(실패는 캐시하지 않음) — 조회 응답 자체는 실패시키지 않는다. 의존성은 핸들러 전에 풀리므로 요청 도중
   활성화되면 옛 토큰이 실린다(소비자 쪽에서 안전한 방향, D7).
8. **"일부러 빨갛게" 기록.** 표 10개 각각을 지문 spec에서 빼기, `mv_geocode_target` 빼기, `ST_NPoints` 빼기,
   `bulk_id` 해시, 성공 경로 savepoint RELEASE, 활성화 캐시 삭제 제거, 캐시 삭제를 지문 계산 여부에 결박, 지문을 lock
   안으로 이동, `notes` 접미 제거 — 18개 변형 모두 해당 통합 테스트가 실패함을 확인했다(PR 본문). lint는 가짜
   `JOIN tl_new_table`·유령 허용 항목·집합에서 표 제거에 빨갛고, 일반/`MATERIALIZED`/`NOT MATERIALIZED` CTE와
   `JOIN generate_series(` 추가에는 초록이다.

**재실측(1차 리뷰 반영 뒤, 9표 + 열 대조, 2026-10-13 13:47Z).** 5회: **485.8 s 성공**(지문 `dd1-2689bb39…`, drift 없음) —
그러나 그때 n150은 다른 작업으로 load 10~20, IO pressure some 70~95%였다(성공 측정 3·4회의 57/103 s는 조용할 때). 즉
**경합 시 10 min의 81%까지 간다.** 조용한 시간대 재측정은 하지 않았다(prod에 스캔을 더 얹지 않으려고).

**소유자 결정(2026-10-13): 경합 시 fail-open을 수용하고 지렛대는 더 쓰지 않는다.** 근거: (a) prod 활성화는 드물다 —
90일간 2회(2026-08-26 `daily_delta`, 2026-09-28 `manual_rebuild`, 둘 다 73~96 min짜리 `mv_refresh` job 안), hot-swap·
rollback·standalone 적재 활성화는 이력상 0회; (b) 485.8 s도 성공이었고 fail-open은 600 s 초과뿐; (c) NULL의 소비자 비용은
지연뿐(Map ADR-109 결정 5·8) — 틀린 판정 없음; (d) 남은 지렛대는 변화 감지력을 깎는다(정확성 > 실측 성능, ADR-066).
"50% 초과 시 재검토"(결과(부정))는 **조용한 시간의 측정**(57/103 s)에 적용한다. **운영 규칙**: 활성 릴리스에 `data_token`이
없으면(알림 `ktg_data_fingerprint_failures_total`·`notes` 접미) IO 경합이 가라앉은 뒤 `ktgctl serving fingerprint-active`
1회. **재검토 조건**: 조용한 시간 측정이 300 s를 넘거나, 연속 두 활성화가 `timeout`으로 fail-open하거나, 활성화가 주 1회
이상이 되면 지렛대를 다시 연다.

### 구현 기록 — 적대 리뷰 1차(2026-10-13, PR #573 head `b559d3e` 대상 2명) 반영

9. **(H1) 지문은 활성화 lock 앞에서 계산하되, lock 뒤에 낡았는지 다시 본다.** READ COMMITTED에서 스캔 snapshot은
   lock보다 이르므로, 스캔 사이에 다른 활성화가 commit되면 더 새 데이터를 가진 릴리스를 옛 지문으로 덮을 수 있었다.
   이제 스캔 직전에 활성 `serving_release_id`를 읽고(`FingerprintAttempt.active_release_id_before`), lock 뒤
   `previous_release_id`와 다르면 지문을 버리고 `data_fingerprint_failed: superseded_during_scan`(NULL, 판정 불가)로
   기록한다. lock 안 재계산은 하지 않는다 — lock(과 호출자의 다른 잠금)을 스캔 시간만큼 잡게 되기 때문이다. **이 경합에서
   NULL을 받는 쪽은 늦게 끝나 앞선 활성화를 대체하는 활성화 자신이다**(앞선 활성화는 자기 지문을 가진 채 superseded가 된다).
   그래서 경합 직후 활성 릴리스는 `data_token`이 없고, 다음 활성화나 D9 backfill이 고친다. 이 경우는 경고 로그와
   `ktg_data_fingerprint_failures_total{reason="superseded_during_scan"}`로 드러난다(모든 fail-open 사유가 같은 카운터).
10. **(H2) `geo_cache` 키에 release를 넣는다.** 활성화 DELETE 직후 옛 데이터로 계산을 끝낸 in-flight 요청이 다시 쓴 행이
    새 토큰 아래 30일 살아남는 창(결과(부정)에 "알고 받아들인다"로 적었던 것)을 닫는다. 키의 release는
    `version_token`이고, v2 응답의 `dataset`과 **같은 `DatasetRef` 값**에서 온다 — 스탬프를 라우터 의존성에서
    `AsyncAddressClient`로 옮겨, v2 메서드가 요청당 한 번 읽어 캐시 키와 응답에 함께 쓴다(`api/dataset_ref.py` 삭제 →
    `infra/dataset_ref.py`). 활성화 DELETE는 이제 최적화일 뿐이다. v1 엔드포인트도 같은 키 규칙을 쓴다. 스탬프가 없으면
    (활성 릴리스 없음·원장 조회 실패) 답을 release에 묶을 수 없으므로 결과 캐시를 읽지도 쓰지도 않는다(2차 리뷰).
11. **(H3) `record_mv_refresh_release`는 `publication_guard` 전에 스캔한다.** guard는 `load_jobs` 행을 `FOR UPDATE`로 잡고
    `lock_timeout='5s'`를 transaction 끝까지 남긴다 — 그 안에서 스캔하면 cancel·`renew_lease`·`set_progress`가 스캔 내내
    막히고(300 s lease 만료 → reconciler가 정상 job을 죽일 수 있음) 5 s lock_timeout이 스캔에 샌다. 스캔은 `mv_hash` 옆에서
    하고 결과를 `fingerprint_attempt`로 넘긴다(실패해도 "계산했고 실패" 상태로 넘어가 `notes` 접미가 그대로 붙는다).
12. **(M1) 지문 표는 9개다.** `zip_repo`는 v1 `/v1/address/zipcode` 전용이라(`client.zipcode` → `api/routers/zipcode.py`)
    `postal_bulk_delivery`·`tl_kodis_bas`를 뺐다(`postal_pobox`를 뺀 것과 같은 이유). lint는 이제 `infra/*_repo.py` 전부를
    스캔하고, 비v2 허용 목록(`admin_repo`·`file_inventory_repo`·`source_upload_repo`·`pobox_repo`·`zip_repo`, 각 사유)의
    클래스가 v2 클라이언트 메서드에 나오지 않음을 함께 단언한다 — v2 경로에서 쓰이는 새 repo는 숨을 수 없다.
13. **(M2) 스캔 전에 열을 대조한다.** `compute_data_fingerprint`가 같은 savepoint에서 `pg_attribute`를 읽어
    "해시·요약·제외·드롭 열 = 실제 열"이 아니면 스캔하지 않고 `schema_drift:<table>`로 fail-open한다.
14. **(M3') 0029 이전 백업 복원.** 읽기는 `to_jsonb(ds) ->> 'data_fingerprint'`로 열이 없어도 동작하고, 활성화는 열이
    없으면 열 없이 INSERT하고 `schema_missing`을 `notes`에 붙인다. hot-swap preflight는 restore DB의 `alembic_version`이
    serving DB와 다르면 rename 전에 거부한다(전용 우회 플래그 `allow_schema_revision_mismatch` — PostgreSQL/PostGIS
    버전용 `allow_version_mismatch`와 분리; 메시지가 `alembic upgrade head`를 안내).
    **배포 노트**: 0029 이전 백업을 hot-swap하려면 restore DB에 먼저 `alembic upgrade head`를 돌린다; replace_current 복원은
    열 없이 기록되며(토큰 없음) 그 뒤 `alembic upgrade head` + `ktgctl serving fingerprint-active`로 복구한다.
15. **(M4, 2차 리뷰로 개정) hot-swap·rollback은 지문을 상속한다.** 해시는 행 순서와 무관한 합이라 dump/restore가 보존한다
    — restore DB의 활성 snapshot(rollback이면 이전 DB의 마지막 활성 snapshot)이 이미 이 데이터의 `data_fingerprint`를 갖고
    있으므로 그것을 그대로 새 릴리스에 싣는다(상속 시 "스캔 전 활성 release"도 그 DB의 것이라 H1 검사가 그대로 성립). 그것이
    없을 때(0029 이전 백업, fail-open이었던 릴리스)만 서빙될 DB를 스캔하며, 그 스캔은 **HOT_SWAP lock 안, rename 전**에
    2분 예산(`HOT_SWAP_FINGERPRINT_TIMEOUT`)으로 돈다 — 차가운 restore DB면 대개 넘으므로 **상속이 없으면 fail-open +
    backfill을 예상한다**. 앱 엔진 팩토리로 연결해 `search_path`(`x_extension` = PostGIS)가 같다 — `create_async_engine`
    원 DSN이면 `ST_NPoints`가 `UndefinedFunction`이었다(라이브 hot-swap 왕복 테스트가 잡음). 왕복 테스트는 상속(스캔 0회,
    토큰 = 심은 지문)과 상속 없는 rollback(이전 DB를 rename 전 이름으로 1회 스캔, 실패 → NULL + 접미)을 모두 단언한다.
16. **(M5) `DatasetRefCache`는 실패를 1초 기억한다** — 원장 조회가 실패할 때 대기자가 lock 뒤에 줄지어 재시도하지 않는다.
17. **(M6) CI `integration-postgis` job.** `postgis/postgis:16-3.5` 서비스 + `ktgctl init-db` + `alembic stamp head` 뒤
    T-325 통합·lineage race·projection·hot-swap 왕복을 돌리고, junit에서 skip 0과 **파일별 하한**(classname 기준)을
    요구한다. 그 전에 `alembic downgrade -1 && alembic upgrade head`로 0029를 실제로 실행하고 열 존재를 확인한다.
18. **(L) 그 밖.** lint가 콤마 조인·`FROM ONLY`·`LATERAL`·schema 한정 이름을 보고, CTE 이름은 모듈 안에서만 뺀다(각각
    빨강 케이스). `mv_geocode_text_search` 허용 근거(출처가 `mv_geocode_target` 하나)를 테스트로 고정. `string_agg` 정렬은
    `COLLATE "C"` — 그래도 PostGIS 버전·바이트 순서가 바뀌면(odroid aarch64 이전 등) `Box2D` 텍스트·`ST_AsBinary`가 달라져
    토큰이 한 번 바뀔 수 있다(ADR-070 D8과 같은 "전량 재계획 1회"). admin `ServingRelease.data_token`도 `dd1-` 패턴.
    backfill CLI는 lock 대기·UPDATE·DELETE를 `statement_timeout 5min`으로 한다(세션 기본 5 s).

## 후속

- (closed 2026-10-13 — 넷 다 추천안 승인, 상태 `accepted`) **소유자 승인 대기 4개(설계 §12 번호 + plan owner_decisions)** — #1 C안(서빙 내용 지문·
  표 집합 유도), #2 fail-open(NULL의 소비자 의미가 "바뀜"이 아니라 "판정 불가"인 것 포함, D5·D8),
  #18 D3 geometry 요약 지문의 한계, **§4a #11** 활성 릴리스마다 `geo_cache` 전체 삭제(D6 — 설계에서
  확정했으나 prod 가시 비용이 있어 plan owner_decisions에 포함). 승인 전까지 상태 `proposed`, 승인
  시 T-325a PR에서 `accepted`로 전환.
- (open) T-325a: PR-1 브랜치 `ktgctl serving fingerprint-active --dry-run`으로 prod 규모 지문
  실측(n150에서, 머지 전 — 2026-10-13 수행, 결과는 "구현 기록" 절) → 50% 기준 판정 → PR-1 머지·배포 → backfill CLI 실행 →
  `current.data_token` 비NULL·`geo_cache` 0행 확인. 배포 순서는 geo → backfill → 소비자 배포
  (소비자 코드 머지는 geo와 병렬 가능, 활성화 검증만 geo 배포 뒤 — 설계 §9/§11; `docs/resume.md`).
- (closed 2026-10-13) `postal_pobox`는 v2 경로에서 읽히지 않는다 — `PoboxRepository`의 호출자는
  `client.pobox`(→ `/v1/address/pobox`) 하나이고, 다섯 v2 repo의 유도 집합에 없다(lint가 고정).
- (open) phase 2 — 코드 단위 인벤토리 diff(`ops.snapshot_code_inventory` + `POST /v2/dataset/changes`):
  소비자의 재처리 우선순위·폐지 코드 finding·하드코딩 시도 표 개편 신호에 쓰인다. 착수 여부는
  소유자 결정(설계 §12 #12). 인벤토리 생성 자리는 D4와 같은 헬퍼.
- (closed 2026-10-13) ADR-067 "하지 않는 것" #6과 D1 "같은 토큰 ⇒ 미변경, 역 비보증" 문구에 amend 표기.
- 구현 뒤 `docs/api-reference/v2/{geocode,reverse,search,regions-within-radius}.md` 응답 예시와
  `docs/api-reference/llm-summary.md`(v2 dataset 행에 `data_token`, 네 조회 행에 `dataset`)에
  반영하고 `dataset-version.md`의 "예정" 절을 현재 규약으로 승격한다(T-325c).
