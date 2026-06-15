# clean-slate v2 정확도 검토: optional 데이터셋으로 상세주소(a)·무주소(b) 정확도 달성 가능성 + 1:N 스키마안 비판

작성일: 2026-06-15
담당: Claude (Agent B)
관련: T-105(v2 재audit), T-125(C11 serving preflight), T-219(v1 vworld 계약 후속), ADR-007/012/038/039/051, `docs/source-data-accuracy-review.md`, `docs/t118-phase1-go-no-go.md`, `docs/t123-phase1-acceptance.md`

성격: **탐색적 설계 분석(critical analysis)** — 확정 ADR/결정이 아니다. Codex(Agent A)가 제시한 optional 데이터셋 활용 의견에 대한 비판적 검토와, "v1 vworld 호환을 폐기하고 v2를 완전 신규 API로 두고 데이터·DB 스키마를 처음부터 새로 설계한다"는 clean-slate 가정의 실현성 평가다.

방법: 다중 에이전트 적대적 분석(ground 5 readers → critique 6 lens → synthesize → red-team, 13 agents). 모든 load-bearing 주장은 실제 코드/문서를 `file:line`으로 대조했다. 핵심 결정 주장(국가지점번호 makarea 게이트, v2 producer의 1:N collapse, v2 wire의 candidate tuple, match_kind/precision enum)은 작성자가 직접 재확인했다. 추정은 "[추정]", 미측정/미검증은 "[미측정]"/"[open]"으로 표시한다. 데이터 품질 C1~C10 ERROR·혼합 기준월은 known issue(버그 아님).

---

## 0. 한눈 요약 — 뭘 쓰고 뭘 안 쓰나

### 0.1 optional 데이터셋별 요약

| 데이터셋 | 결론 | 어디에 쓰나 | 왜 (한 줄) |
|---|---|---|---|
| **국가지점번호 (좌표)** | ✅ **그냥 쓴다** | v2 forward/reverse 무주소 위치 | 좌표를 **계산**으로 만든다(데이터 0). 단 지금은 의무지역 밖이면 막혀 있어 그 빗장만 풀면 됨 |
| **zone_shape (TL_SPPN_MAKAREA)** | ✅ **이미 쓰는 중** | 국가지점번호 표기 의무지역 context | 24,204존, 이미 서빙 중. 단 "정밀 위치"가 아니라 "구역 안내"용 |
| **도로명주소 건물 도형 / 출입구 (C11)** | ⚠️ **조건부 — 아직 보류** | (검증 통과 시) 대표점 정확도 개선 후보 | 유일한 대표점급 후보지만, "현재 대표점보다 정확하다"는 **증거가 아직 없음**(p99 미측정). 검증 전엔 승격 금지 |
| **상세주소DB (detail_address)** | ⚠️ **텍스트만** | 동/호 **목록** 제공 | 동·호 **글자는 있는데 좌표가 없음**. 위치는 부모 건물점을 빌려 씀 |
| **상세주소 동 도형 (detail_dong)** | ⚠️ **부분만** | 상세주소 동(洞) 단위 앵커 | 좌표 있는 건 동 출입구점 42만개뿐(건물 640만개 대비 극소). **호별 좌표는 어디에도 없음** |
| **국가지점번호 grid (shape/center)** | ❌ **서빙엔 안 씀** | CI 검증용으로만 | 100m라 계산값(10m)보다 **더 거침**. 1,000만 행 넣을 이유 없음 |
| **민원행정기관 (POI)** | ❌ **주소 좌표 대체 금지** | (나중에) 별도 장소검색 | 기준월 202401·오차 194m, 주소급 정밀도 미달. POI는 POI로만 |
| **건물DB / 주소DB (building/address_db)** | ❌ **좌표 원천 아님** | 속성·검증 보조 | 좌표 없는 텍스트 속성. 정확도 향상엔 무관 |

### 0.2 가장 쉽게 말하면

- **공짜로 바로 되는 것**: 국가지점번호(주소 없는 곳 위치) — 데이터 추가 없이 빗장만 풀면 끝.
- **되긴 되는데 "대충 위치"까지만**: 상세주소(동/호) — 글자는 다 주지만 좌표는 건물 수준.
- **검증 끝나야 쓰는 것**: 건물 출입구점(C11) — 정확도 이득이 증명돼야 승격.
- **절대 좌표로 쓰면 안 되는 것**: 민원행정기관 POI, grid 소스, 건물/주소DB 텍스트.

핵심 한 줄: **"주소 없는 곳(국가지점번호)"은 지금 당장 가능, "상세주소"는 동 단위까지만, 나머지 optional은 정확도 향상 원천이 아니라 검증·부가정보용.**

### 0.3 도로명주소 건물 도형(C11)만 따로 — "유력한데 아직 안 됨"

이 데이터셋은 두 부분으로 나눠 봐야 한다.

| 구성 | 정확도에 쓸모 | 결론 |
|---|---|---|
| **출입구 점 (TL_SPBD_ENTRC)** | 대표점(=주소 좌표)을 더 정확하게 만들 **유일한** 후보 | ⚠️ **조건부, 보류** |
| **건물 외곽 폴리곤** | 좌표 정확도엔 무관, **건물 모양 표시(v2 geometry)**용 | △ 저위험 별도 용도 |

- **왜 유력**: C11~C17 중 현재 대표점 좌표에 직접 연결될 수 있는 **유일한** 후보, 원천끼리 일치율 거의 100%(p95·max 0.0m).
- **왜 아직 안 됨**(Codex의 "승격 직전"은 과장):
  1. **0.0m의 정체** = *원천끼리(번들↔전자지도)* 일치일 뿐, 현재 서빙 대표점/실측 정답 대비 거리가 **아님**.
  2. **키 단절** — 번들 키(SIG_CD,BUL_MAN_NO,ENT_MAN_NO,EQB_MAN_SN) ≠ 서빙 키(sig_cd,ent_man_no) → 느슨한 키 승격 위험.
  3. **게이트 미달** — 승격 기준 p99≤30m인데 프로토타입이 **p99 미산출**.
  4. **이득 0 가능성** — 이미 base 테이블에 있고 ADR-007이 대표 출입구를 이미 고름 → 비용만 들고 이득 미미할 수 있음.
- **그래서**: 대표점 교체는 **T-125 검증(거리분포 + 정합성/성능 회귀) 통과 후**에만. 단 건물 **외곽 폴리곤**을 v2 `include_geometry`(건물 모양 표시)에 쓰는 건 저위험으로 당장 가능.

---

## 1. 결론 요약 (TL;DR)

clean-slate 전제(v1 vworld 호환 폐기 + 신규 스키마 + 신규 단일월 적재)에서도 정직한 정확도 천장은 다음과 같다.

- **(a) 상세주소 — 조건부 가능, 단 "열거+거친 앵커링"까지.** 단위(동/층/호)별 좌표는 **어떤 optional 데이터셋에도 없다.** 유일한 단위 원천 `detail_address_db`(전국 3,204,565행, `source-data-accuracy-review.md:268`)는 좌표 컬럼이 0개다(`c13_detail_dong.py:88-108`, 로더 주석 `:259-262` "detail_address_db has no geometry"). 좌표를 붙일 수 있는 가장 미세한 도형은 상세주소 동(洞) 폴리곤 `TL_SGCO_RNADR_DONG`과 동 출입구점 `TL_SPBD_ENTRC_DONG`(전국 424,639점)뿐이다. 따라서 (a)는 **door-level(호별) 정밀 geocoding이 아니라 동-폴리곤/건물 출입구에 앵커링한 sub-address 열거(enumeration)**다. 측정된 한계: 동 출입구점의 자기 동 폴리곤 포함률 96.48%(409,672/424,639, `t123:48`).

- **(b) 무주소 (국가지점번호) — 이미 가능, 데이터 추가 0.** 좌표는 **데이터가 아니라 코드로 합성**된다. `parse_national_point_number`가 EPSG:5179 10m 셀 중심을 문자열에서 계산한다(`sppn.py:38-70`). optional grid(C14)는 최저해상도 100m로 오히려 더 거칠고 `serving_promotion=False`(`c14:176-183`); T-118이 "현 core/sppn.py의 10m 좌표 계산보다 더 정밀한 좌표 원천이 아니다"라고 명시(`t118:64`). 다만 현재 forward는 makarea 게이트 때문에 의무지역 밖 유효 코드를 `NOT_FOUND`로 죽인다(`geocoder.py:91-96`) — **버그가 아니라 capability gap**이고 clean-slate에서 해소 가능하다.

- **(b)' 무주소 "명명된 장소" POI(산/들/해안 trailhead 등) — 불가(serving-grade 소스 부재).** 유일 후보 C15(민원행정기관)는 기준월 202401, p95 194.350m, 100m 초과 14.054%, `serving_promotion=False`(`t123:50`, `c15:122`).

**핵심 권고**: 1주소 1대표점 계약은 깨되 **"플랫 1:N 단일 MV"는 채택하지 말 것.** ① 엄격 UNIQUE 대표점 MV(빠른 CONCURRENTLY refresh·LIMIT-1 라우터 유지) + ② query-time join하는 typed 1:N 보조 테이블(다중 출입구/상세주소/POI) + ③ 무주소는 parser 계산 + makarea zone context로 분리한다. v2 wire 계약(`candidates: tuple[CandidateV2,...]`, `dto/v2.py:79-91`)이 이미 1:N을 지원하므로 **public 스키마 변경 없이 producer만 1:N으로** 만들면 된다.

---

## 2. 1:N 스키마안에 대한 비판적 평가 (무엇이 깨지고 무엇이 이득인가)

먼저 1주소 1대표점 계약이 **물리적으로 어떻게 강제되는지** 확인했다.

- `mv_geocode_target`은 `SELECT DISTINCT ON (bd_mgt_sn)`로 빌드되고(`sql.py:1212`) `UNIQUE INDEX idx_mv_geocode_target_pk (bd_mgt_sn)`로 잠긴다(`sql.py:1299`). 대표점은 `tl_locsum_entrc`(priority 0)→`tl_roadaddr_entrc`(priority 1), `ent_se_cd='0'` 우선, `ent_man_no`, centroid fallback 순으로 1점을 고른다(`sql.py:1220-1296`).
- forward는 `LIMIT 1`로 0/1행 보장(`geocode_repo.py:54,89`), 파생 `mv_geocode_text_search`도 UNIQUE(`sql.py:1349-1350` 영역), search/fuzzy는 `bd_mgt_sn` 유니크를 가정한 join-back(`search_repo.py:84-85`, `geocode_repo.py:117-118`)이며 pagination `count(*) OVER ()`도 이 유니크에 의존한다.
- refresh/swap은 UNIQUE 인덱스 위에서 `REFRESH MATERIALIZED VIEW CONCURRENTLY`를 쓰거나(`postload.py:59-65`) shadow-swap으로 인덱스 rename(`postload.py:52-57`)한다.

**판정: 1:N 스키마는 clean-slate에서 구조적으로 건전하고 올바른 방향이다. 그러나 두 가지를 반드시 분리해서 봐야 한다.**

**(가) 깨지는 것은 v1 호환이 아니라 ADR-007의 운영 이득이다.** 1:N의 진짜 비용 — UNIQUE(bd_mgt_sn) 상실, CONCURRENTLY refresh 위협, LIMIT-1 라우터 단순성 상실, search dedup/pagination total 재정의 — 는 **v1 vworld 호환과 무관**하게 발생한다(ADR-007 근거 `decisions.md:440`). clean-slate가 v1 게이트를 없애 준다고 해서 이 비용이 사라지지 않는다. **단, 복합 UNIQUE 키((address_id, sub_id) 또는 location_id)도 Postgres의 CONCURRENTLY 요건(어떤 유니크 인덱스든 존재)을 충족하므로** [확인: Postgres 동작상 사실; 본 프로젝트에서 직접 테스트는 미수행, open], 대표점을 별도 UNIQUE MV로 유지하면 이 이득은 보존 가능하다. → "플랫 단일 1:N MV"는 비용만 떠안고 이득을 버리는 최악수이므로 기각한다.

**(나) 사는 것은 "candidate-list 열거 + typed precision"이지 "좌표 정확도 향상"이 아니다.** 1:N이 추가로 surface하는 점들(비대표 출입구 등)은 이미 base 테이블(`tl_locsum_entrc`, `tl_navi_entrc`)에 존재하고 ADR-007이 직접조회로 우회시켜 둔 것(`decisions.md:449`)이다. 즉 1:N은 **데이터를 발명하지 않고 노출**할 뿐이다. 그리고 그 노출이 좌표를 더 정확하게 만들지는 않는다(아래 근거별 검증 참조).

### 데이터셋별 검증 (방향은 맞으나 "정확도" 주장은 과장)

**C11 (출입구점) — 유일한 대표점-인접 후보, 그러나 승격 근거 미측정.**
- 방향 정확: C11~C17 중 유일하게 대표점 좌표와 연결될 수 있는 후보다(`t118` 결론, ADR-051). C12~C17은 대표점 없음/검증 전용.
- **과장 주의 1**: T-123의 0.0m는 **원천 대 원천 일치**(roadaddr bundle ↔ 전자지도 TL_SPBD_ENTRC full key)일 뿐, **현재 서빙 대표점 대비 거리도, 측량 정답 대비 거리도 아니다.** C11 프로토타입은 `_measure_pair`만 돌리고 `mv_geocode_target.pt_5179`를 건드리지 않는다. "0.0m → 승격 직전"으로 읽으면 오독이다.
- **과장 주의 2**: 키 네임스페이스 단절. bundle full key는 `(SIG_CD, BUL_MAN_NO, ENT_MAN_NO, EQB_MAN_SN)`(`building_shape_bundle.py:47`)인데 서빙 테이블 `tl_locsum_entrc` PK는 `(sig_cd, ent_man_no)`로 `BUL_MAN_NO/EQB_MAN_SN`를 버린다(`sql.py:115`). 그래서 bundle↔locsum/roadaddr는 약한 키 join만 가능하다(`c11:254-257`). **full key로 검증한 일치를 weak key로 승격하는** 위험이 있다.
- **게이트 미달**: 프로토타입 `DistanceMeasurement`는 p50/p95/max만 내고 **p99가 없다**(`augment_harness.py`). ADR-051/T-125는 p99≤30m을 요구한다(`t118:116`, `t125`). 계기 재작성이 선행돼야 한다.
- 숫자: intersection 6,405,305 / left 0.992367 / right 0.999943 / p95·max 0.0m — `t123:46` 일치. **확정.**

**C13 (상세주소) — cardinality 단절 실재, "별도 API"는 거짓 이분법, "정확도 향상"은 과장.**
- 방향 정확: 같은 MV에 상세주소를 펼치면 UNIQUE/DISTINCT ON/LIMIT-1/text-search MV/swap이 모두 깨진다(위 (가)). 상세주소 텍스트 DB가 직접 좌표 소스가 될 수 없다는 것도 옳다(`c13:259-262`).
- **거짓 이분법 교정**: "대표 MV를 공유하면 안 된다"(참)와 "별도 엔드포인트여야 한다"(불필요)는 다르다. v2 wire는 이미 `candidates: tuple[CandidateV2,...]`로 1:N을 모델링하므로(`dto/v2.py:79-91`) **같은 `/v2/geocode` 안 typed candidate 스트림**으로 first-class 노출 가능하다.
- **정확도 과장 교정**: `TL_SGCO_RNADR_DONG`는 건물군 동(101동/102동급) 폴리곤이지 호별이 아니다. 폴리곤 자체는 6,454,292개로 건물 스케일이지만(`source-data-accuracy-review.md:223`), **전자지도 building polygon `TL_SPBD_BULD`의 부분집합**이라 전체 건물을 덮지 못한다(`decisions.md:1539`, `:1575`). 유일 점 레이어 `TL_SPBD_ENTRC_DONG`는 424,639점뿐이며 "모든 상세주소 동 폴리곤에 제공되지 않는다"(`decisions.md:1546`). **호별 좌표는 데이터 어디에도 없다.**
- **메트릭 오독 교정**: C13 0.9648은 "동/호 문자열→정답점 거리"가 아니라 **동 출입구점의 자기 동 폴리곤 포함률(geometric self-consistency)**이다. 단위 수준 위치 정확도 메트릭은 어떤 validator도 내지 않는다(detail_address는 building-level boolean flag로만 LEFT JOIN). **단위 ground-truth 정확도는 repo 어디에도 측정 없음.**
- **부모점도 거칠다**: C15 정확키 매칭에서 p95 194.350m, 14.054% >100m(`t123:50`). 부모 건물점이 1/7 확률로 100~200m 어긋나는데 그걸 상속한 호점을 "더 정확"하다 광고할 수 없다.
- 숫자: containment 409,672/424,639 = 0.964754 — `t123:48` 일치. **확정.**

**C14 (국가지점번호 grid) + makarea — Codex 옳음, 단 "이미 충분히 서빙"은 과장.**
- 코드로 확정: 국가지점번호 좌표는 grid 파일이 아니라 `sppn.py:38-70`이 합성한다(`X_ORIGIN_5179=700000`, `GRID_SIZE_M=100000`, `CELL_SIZE_M=10`, +5 셀 중심). grid는 최저 100m(`c14:44-49`), parser 10m보다 거칠고 검증 전용(`c14:176-183`, `t118:64`). makarea(`tl_sppn_makarea`, 24,204존)는 별도 테이블로 zone context를 이미 서빙(`geocode_repo.py:126-147`, match_kind='sppn').
- **과장 교정**: forward가 인위적으로 불구다. parser가 정밀 점을 계산해 놓고도 makarea 폴리곤에 안 걸리면 `NOT_FOUND` 반환(`geocoder.py:91-96`, 코드로 확정). **24,204 의무존 밖의 유효 국가지점번호는 좌표가 있어도 안 나온다.** "이미 서빙" 프레임이 이 gap을 가린다.
- **추가 리스크**: parser bound-check가 헐겁다. `_cell_index`는 offset<0 / grid_index>=14 / digit>=10000만 거른다(`sppn.py:88-99`). EPSG:5179 유효 범위만 보고 한국 실제 육지/grid envelope를 제약하지 않아 바다·국경 밖 코드에도 좌표를 뱉을 수 있다 — clean-slate에서 노출 확대 시 bound-check 필요.
- **reverse 미배선**: `format_national_point_number_from_5179`(`sppn.py:73-99`)는 존재하고 테스트되지만 C14 검증에만 배선됐다. reverse에서 코드를 first-class로 방출해야 하는데 — 순수 계산, 신규 데이터 0.
- 숫자: grid/center 10,184,741 / formatter parent mismatch 0 / 1km bbox·center mismatch 1,489 — `t123:49` 일치. **확정.**

**C15 (POI) — 분류는 옳음, "POI 품질 미달" 단정은 메트릭상 과도.**
- 방향 정확: POI이지 주소 정본 아님(`c15:115-122` "does not add institution names or POI coordinates to normal address candidates", `serving_promotion=False`). 좌표를 POI 점으로 대체하면 ADR-051 게이트(p95≤10m, outlier≤0.1%)를 ~19배·~140배 초과 — 좌표 대체 금지는 옳다.
- **메트릭 해석 교정**: 194.350m/14.054%는 "POI 품질"이 아니라 **"POI점 vs 주소 대표점" 양방향 불일치**다. SQL은 정확 도로키 join 후 `ST_Distance(p.geom, t.pt_5179)`(`c15:360-374`). 책임이 (i) POI 품질인지 (ii) 대형/캠퍼스 건물에서 ADR-007 단일 대표점이 거친 탓인지 (iii) 202401 vs 202603/604 월 drift인지 **분리 불가**다. "POI는 주소급 아님"을 이 숫자만으로 단정할 수 없다.
- **죽은 표면 교정**: `SearchRepository.search`는 place/category에 `([],0)` 반환(`search_repo.py:241-242`, 확인). "재라우팅"이 아니라 신규 serving POI 테이블+producer 신규 구축이다.
- **enum 정밀도**: enum에 'place'는 없다(`dto/v2.py:15`: road/parcel/postal/keyword/category/region/sppn). 본 프로젝트 문서는 상세주소에 `match_kind="detail"`을 이미 제안한다(`source-data-accuracy-review.md:253`). clean-slate라면 'keyword' 과적재 대신 명시적 `'poi'`(POI)·`'detail'`(상세주소)을 추가하라.
- 숫자: parse 100% / match ratio 0.976742 / p95 194.350m / 100m 초과 14.054% — `t123:50` 일치, 소수 3자리까지 정확. **확정.** 보강: 문서·코드 모두 **p99 없음**(`c15:399-401`은 percentile_cont 0.5/0.95 + max만) — T-125 게이트 요구 미달.

---

## 3. clean-slate v2 데이터 모델안 (typed 1:N location 모델)

설계 원칙: **1:N을 허용하되 플랫 단일 MV로 펼치지 말 것.** ADR-007의 운영 이득(UNIQUE→CONCURRENTLY, LIMIT-1 0/1행)을 보조 1:N 테이블과 분리하여 보존한다.

### 3.1 엔티티 (신규 스키마, 예: `geo`)

1. **`address_core`** — 정본 주소 정체성. PK `address_id`(합성). `bd_mgt_sn`은 PK가 아닌 비유니크 속성으로 강등. 도로/지번/region 컬럼(오늘 `tl_juso_text` + `sql.py:1255-1278` 투영). **좌표 없음.** ~6.4M행.
2. **`location_point`** — typed 1:N 점 테이블. PK `location_id`; FK `address_id`(무주소는 NULL); `geom_5179`(GiST)/`geom_4326`; `point_type ENUM {entrance, navi_centroid, building_centroid, parcel_centroid, detail_dong_entrance, poi, grid_cell_center}`; `point_precision {exact, interpolated, centroid, approximate, grid_cell}`; `is_representative bool`; `source_table`/`source_yyyymm`; `sub_ref`(동/층/호 serial); `confidence`. 오늘 `pt_5179/pt_source`(`sql.py:1279-1288`)와 ADR-007이 직접조회로 우회한 비대표 출입구(`decisions.md:449`)를 흡수.
3. **`addressless_feature`** — PK `feature_id`; `feature_type {national_point_grid, makarea_zone, poi_standalone}`; geom; precision; metadata. 국가지점번호는 **parser 계산 유지**(10M행 grid 테이블 불필요). makarea(24,204)는 zone context로 이전. 주소 미연결 standalone POI(C15) 수용.
4. **`place`** — PK `place_id`; FK `location_id`; name/category/phone/url(`PlaceV2`, `dto/v2.py:64-69`). POI는 주소 후보에 융합하지 않고 `location_point`에 연결.

### 3.2 대표점 = 구조적 제약이 아니라 flag/materialized 선택

ADR-007 선택 로직(`sql.py:1212-1296`)을 `location_point.is_representative=true`로 materialize. default geocode는 ADR-007 이득을 전부 보존하면서 다른 typed 점도 주소화된다.

### 3.3 서빙 MV 전략 (CONCURRENTLY 유지) — 트레이드오프 정직 명시

- **`mv_address_rep`**: `address_id`당 1행 WHERE `is_representative`. **UNIQUE(address_id) → CONCURRENTLY OK.** 도로/지번 LIMIT-1(`geocode_repo.py:41-91`) 형태 불변. 오늘 인덱스셋(`sql.py:1299-1324`) 유지.
- **`mv_address_points`**: 1:N `(address_id, location_id)`, **UNIQUE(location_id)**. Postgres CONCURRENTLY는 어떤 유니크든 있으면 되지만, 이 복합 키로 실제 CONCURRENTLY가 유지되는지는 **본 프로젝트에서 미검증 [open]**. detailed/all-points 모드 전용.
- **`mv_text_search`**: `mv_address_rep`에서 1:1 파생(`sql.py:1331-1347` 형태 불변).
- **무주소**: parser + zone/feature lookup으로 서빙(MV 비대화 없음).
- **트레이드오프(정직)**: (1) `mv_address_points`는 평균 건물당 점수만큼 행·GiST/btree 인덱스·CONCURRENTLY working set 증가 — **평균 건물당 출입구 수는 어디에도 기록 없음 [open]**, 따라서 배수 미상. (2) **swap 파이프라인이 복잡해진다**: 오늘 단일 swap(`postload.py:52-57`)이 이제 `mv_address_rep`+`mv_address_points`+`mv_text_search`를 **원자적으로** 조율해야 하며, 부분 swap은 cross-MV 불일치를 만든다 — ADR-007 대비 실제 추가 운영 표면.

### 3.4 reverse / dedup / pagination — 깨지는 지점과 재정의 (정직)

- **reverse(`reverse_repo.py:33-35,92-98`)**: 오늘은 GiST k-NN + `LIMIT :limit`이고 `address_type='both'`가 행을 2배로 만든다. 1:N에서는 한 건물의 다수 sub-point가 최근접 리스트를 같은 주소로 도배 → **default는 "건물당 최근접 1점 collapse"(오늘 동작 유지)**, opt-in으로 'all typed points' 모드. both×point_type fan-out이 곱셈으로 터지지 않게 typed grouping 규약 필수.
- **search/fuzzy(`search_repo.py:84-87`, `geocode_repo.py:117-118`)**: 1:N MV로 join하면 fan-out으로 결과·`count(*) OVER ()` total이 부풀려진다. → default join-back은 `mv_address_rep`(UNIQUE) 대상으로 유지, all-points 모드만 `mv_address_points`를 `GROUP BY address_id` dedup. **pagination total = collapse 모드 `count(DISTINCT address_id)`, all-points 모드 `count(*)`** — 모드 인지형으로 명시.
- **wire 영향 0**: CandidateV2는 1:N을 이미 표현 가능(`dto/v2.py:79-91`)하나, 현재 producer `geocode_v2_from_v1`는 1개로 collapse한다(`core/v2.py:31-56`, 확인). **public 스키마 변경 없이 producer만** 다점 방출하면 된다. 단 1:N 후보 dedup/주소화를 위해 CandidateV2에 명시적 `point_type` + 안정 `candidate_id` 추가 권장(오늘은 metadata dict가 유일 탈출구).

---

## 4. 두 목표별 가능/조건부/불가 판정

### (a) 상세주소 — **조건부 가능(열거·동-level 앵커), door-level 불가**

| 항목 | 판정 | 근거 |
|------|------|------|
| 동/호 문자열 열거·구조화 | ✅ 가능 (3,204,565 단위행) | `c13:88-108`; `source-data-accuracy-review.md:268` |
| 동(洞) 폴리곤 앵커링 | △ 부분 (전체 건물 미커버) | `TL_SGCO_RNADR_DONG`(6,454,292)는 `TL_SPBD_BULD`의 **부분집합** `decisions.md:1539,1575` |
| 동 출입구점 앵커링 | △ 424,639점만 (vs 6.4M 건물) | `decisions.md:1546` "모든 폴리곤에 제공 안 됨"; `source-data-accuracy-review.md:224` |
| **호별(door-level) 좌표** | ❌ 불가 | 어떤 optional 데이터에도 단위 좌표 없음 (`c13:259-262`) |
| 측정된 천장 | 동출입구 포함률 96.48% | `t123:48` |

**판정**: (a)는 **first-class 기능화 가능**(같은 `/v2/geocode`의 `match_kind='detail'` 후보)이나, 좌표는 동-폴리곤/건물출입구 grade이고 대다수 호는 부모 건물점과 동일하다. `point_precision`을 정직하게 'approximate'/'centroid'로 강등해야 한다. **동출입구점 없는 압도적 다수 호에 대한 fallback 규칙(부모 대표점) 정의 필수 — 현재 미정의 [open].**

### (b) 무주소 — 국가지점번호 **이미 가능(계산)**, 명명 장소 POI **불가**

| 항목 | 판정 | 근거 |
|------|------|------|
| 국가지점번호 forward 좌표 | ✅ 이미 가능 (10m 셀, 데이터 0) | `sppn.py:38-70` |
| grid 소스 필요? | ❌ 불필요 (100m, 더 거침, 검증 전용) | `c14:44-49,176-183`; `t118:64` |
| forward 의무존 밖 커버 | ⚠️ 현재 막힘 → clean-slate에서 해제 가능 | `geocoder.py:91-96` (makarea 게이트→NOT_FOUND) |
| reverse → 국가지점번호 코드 | ✅ 계산 가능, 미배선 | `sppn.py:73-99` |
| makarea zone context | ✅ 이미 서빙 (24,204존) | `geocode_repo.py:126-147` |
| 한국 육지/envelope bound-check | ⚠️ 없음 → 바다/국경 밖 좌표 산출 가능 | `sppn.py:88-99` |
| **무주소 명명 장소 POI**(산/들/해안) | ❌ serving-grade 소스 없음 | C15 202401/p95 194.350m/14.054% `t123:50` |

**판정**: (b) 국가지점번호는 **데이터 추가 0**으로 충족된다 — forward를 makarea 게이트에서 분리(존 밖이면 점은 계산값 반환, makarea는 선택적 enrich로 강등)하고 reverse에 formatter를 배선하면 된다. 단 envelope bound-check 추가 필요. **무주소 명명 장소 POI는 별도 미해결 데이터 문제**다(serving-grade·라이선스 정리된 신규 소스 필요).

---

## 5. 비용/리스크와 데이터 품질 caveat

### 싸게 되는 것 (compute, 신규 소스·MV 0)
- (b) 국가지점번호 forward 노출 + makarea 게이트 분리 + reverse 코드 방출 + envelope bound-check — 전부 parser 계산.
- v2 candidate-list 1:N producer — wire는 이미 지원(`dto/v2.py:79-91`), `core/v2.py:31-56`가 1개로 collapse할 뿐. producer만 N개 방출.
- 죽은 enum 정리(`postal`/`category`는 producer가 한 번도 안 냄, `cache`도 미사용) + T-105 envelope/pagination/error 일관화 — 새 스트림 얹기 전 토대.

### 비싼데 한계이득
- **C11 다중 출입구를 대표 MV에 융합**: 0.0m는 원천 일치일 뿐 대표점 대비 정확도 델타 미입증. MV·모든 인덱스·CONCURRENTLY working set이 건물당 점수 배수만큼 증가. 평균 건물당 출입구 수 미기록 [open]. C11이 `best_entrc`가 이미 고른 점을 대부분 재현한다면 정확도 이득 ~0인데 비용은 실재 [추정: 재현 가능성 높음, 미측정].
- **(a) 상세주소 3.2M 단위 + 6.45M 동폴리곤 테이블**: refresh working set·인덱스 증가, 복합키 CONCURRENTLY 유지 가능성 미검증 [open]. 이득은 "열거+거친 앵커"뿐.
- **POI serving 테이블**: C15는 serving 불가(202401/194m), 신규 검증 소스 필요. `search_repo`는 place/category에 빈 결과(`:241-242`) — 전부 신규 구축.

### 데이터 품질 caveat (모두 known issue, 버그 아님)
- **혼합 기준월**: JUSO 202603 / LOCSUM·NAVI 202604 / detail·bundle ~202605 / grid 202405 / POI 202401(`CLAUDE.md`, `t118:20-21`). **어떤 optional 데이터셋도 단일 일관 월을 공동 제공하지 않는다.** 자식 점(202401/202405)을 부모(202603/604)에 앵커링하면 C10/C3-C7 WARN/ERROR로 표면화 — 설계상. clean-slate가 단일월 재적재를 *허용*하지만, **모든 데이터셋이 한 공통월에 동시 존재하는지 미확인** [open]. 정확도 주장은 이 단일월 재적재가 전제되며, 현 측정값은 혼합월에서 나온 것이다.
- **C16/C17 bd_mgt_sn 직접 교집합 0**(`t123:51-52`) — 월/키 drift + 좌표 0(coordinate_load=False)으로 텍스트→서빙 geometry 브릿지 불가.
- **메트릭 정체 정리**: C11 0.0m는 원천 대 원천(정답·현 대표점 대비 아님), C13 0.9648은 포함률(self-consistency), C14 0 mismatch는 parser가 공식 grid와 일치(정답 아님). **단위·무주소 ground-truth 정확도는 repo 어디에도 측정 없음.** 정확도 주장을 떠받칠 ground-truth가 부재하다.
- **측정 출처**: 모든 전국 숫자는 T-121/T-123 일회성 프로토타입 런이고, run-validation은 metric validator를 inline 실행하지 않는다(`consistency_run_validation.py` presence/integrity 게이트만). **serving-time impact harness 부재** — 승격 시 정확도는 현재 미측정.
- **rollback/게이트**: shadow-swap이 유니크 인덱스셋 rename(`postload.py:52-57`) — 1:N 복수 MV는 flag-off rollback rehearsal과 row-count/sample-hash baseline 일치 체크(`t125`)를 복잡하게 만든다. 프로토타입은 p99 미산출이라 T-125 게이트를 그대로 못 채운다.

---

## 6. 권고 로드맵 (clean-slate라도 우선순위)

### v2 first-class (저비용, 정직한 이득)
1. **국가지점번호 forward를 makarea 게이트에서 분리** + reverse 코드 방출. parser 계산값을 `match_kind='sppn'` / `point_precision='grid_cell'`(10m 셀 bbox 명시). makarea는 suppress가 아니라 enrich. **신규 데이터 0.** 한국 육지/grid envelope bound-check 추가.
2. **v2 producer를 1:N candidate-list로** 전환(wire 무변경) + 죽은 enum(postal/category/cache) 정리 + T-105 envelope/pagination/error 모델 일관화.
3. **typed location 모델 도입**: `address_core` + `location_point`(is_representative flag) + `mv_address_rep`(UNIQUE, CONCURRENTLY 유지) + `mv_address_points`(UNIQUE(location_id)). 대표점 빠른경로 보존하며 1:N 잠금해제.

### v2 first-class지만 "열거" 라벨 (중비용, 정직 표기 필수)
4. **상세주소(a)**: `tl_subaddress_unit`(detail_address_db) + 동폴리곤/동출입구 앵커, query-time join, `match_kind='detail'`, `point_precision`을 'approximate'/'centroid'로 정직 강등. door-level 광고 금지. 동출입구 없는 호의 부모-대표점 fallback 규칙 명시.

### overlay / validation 전용 (서빙 비대화 금지)
5. **C14 national_point_grid**: serving 테이블화 금지(10M행·100m·202405). CI 검증 fixture로만(`formatter_parent_mismatch=0` 유지 보증).
6. **makarea**: zone context 후보로 유지(low-confidence, makarea_nm 중복 가능 — 정밀 locator로 광고 금지).

### 보류 (게이트 미충족 / 신규 데이터 필요)
7. **C11 대표점 승격**: clean-slate라도 정확도(현 대표점/단일월 baseline 대비 p50/p95/**p99**/max), 회귀, perf, refresh-feasibility 게이트는 여전히 필요·미충족. 프로토타입 p99 미산출부터 해결. (v1 호환 노출·v1 대비 flag/rollback 게이트는 clean-slate에서 탈락하나 나머지는 유효.)
8. **무주소 명명 POI(산/들/해안)**: serving-grade·라이선스 정리된 신규 소스 부재. C15(202401/194m/`serving_promotion=False`)로는 불가. 별도 place 스트림으로 격리, 진짜 소스 확보 전까지 보류.

---

## 부록: 핵심 숫자 검증 결과 (직접 대조)

| 항목 | 인용값 | 문서/코드 실제값 | 판정 |
|------|--------|------------------|------|
| C15 match ratio | 0.976742 | `t123:50` 0.976742 | ✅ 확정 |
| C15 p95 | 194.350m | `t123:50` 194.350m | ✅ 확정 |
| C15 >100m | 14.054% | `t123:50` 14.054% | ✅ 확정 |
| C11 intersection | 6,405,305 | `t123:46` 6,405,305 / right 0.999943 / p95·max 0.0m | ✅ 확정 |
| C13 containment | 409,672/424,639 | `t123:48` = 0.964754 | ✅ 확정 |
| C14 | 10,184,741 / 1,489 | `t123:49` mismatch 0 / 1km 1,489 | ✅ 확정 |
| detail_address 행수 | 3,204,565 | `source-data-accuracy-review.md:268` | ✅ 확정 |
| TL_SGCO_RNADR_DONG | ~6.45M (subset) | `:223` 6,454,292; `decisions.md:1539` subset | ✅ 확정 |
| TL_SPBD_ENTRC_DONG | 424,639 | `:224` 424,639 | ✅ 확정 |
| SPPN forward 게이트 | makarea None→NOT_FOUND | `geocoder.py:91-96` | ✅ 확정 |
| v2 producer collapse | 1 candidate | `core/v2.py:31-56` | ✅ 확정 |
| C15 p99 | 없음 | `c15:399-401` (0.5/0.95/max만) | ✅ 확정 |
| match_kind 'place' | enum에 없음 | `dto/v2.py:15` | ✅ 확정 |

**정정·보강 요약**: (1) C11 0.0m는 원천 대 원천 일치 — 대표점/정답 대비 아니며 "승격 직전"으로 읽으면 오독. (2) C15 194m/14%는 POI vs 대표점 양방향 불일치라 POI 단독 품질로 단정 불가. (3) C11·C15 프로토타입 모두 p99 미산출 — T-125 게이트 미달. (4) 상세주소 권장 enum은 본 프로젝트가 이미 제안한 `'detail'`(`source-data-accuracy-review.md:253`); POI는 `'poi'` 신설 권고. (5) 국가지점번호 forward의 makarea 게이트→NOT_FOUND는 "이미 서빙" 프레임이 가린 capability gap이며 clean-slate에서 해소 가능. (6) `TL_SGCO_RNADR_DONG`는 폴리곤 수는 건물 스케일(6.45M)이나 building polygon의 부분집합이라 전체 건물 미커버 — 폴리곤 희소가 아니라 *부분집합* 관계가 한계의 본질.

관련 파일(repo 상대경로): `src/kortravelgeo/core/sppn.py`, `core/geocoder.py`, `core/v2.py`, `dto/v2.py`, `infra/sql.py`, `infra/geocode_repo.py`, `infra/reverse_repo.py`, `infra/search_repo.py`, `loaders/postload.py`, `loaders/c11_entrance_sources.py`, `loaders/c13_detail_dong.py`, `loaders/c14_national_point_grid.py`, `loaders/c15_civil_service_poi.py`, `loaders/consistency_run_validation.py`; `docs/t118-phase1-go-no-go.md`, `docs/t123-phase1-acceptance.md`, `docs/t125-c11-serving-preflight.md`, `docs/decisions.md`, `docs/source-data-accuracy-review.md`.
