# T-057: 행정구역 hint(`sig_cd` / `bjd_cd`) 기반 검색 가속

## 상태

- 상태: 설계 (구현 전)
- 대상 브랜치: `agent/<agent>-t057-*`
- 사용자 RFC: 2026-05-27 — "법정동 혹은 시군구코드를 제시하고 검색을 시키면 좀 더 빠른지 확인. 가능하다면 신규 API 및 함수에도 반영할 것. 예: 주소상 서울특별시 안에 있는게 확실한 좌표인 경우."

## 목적

호출자가 "좌표가 서울특별시(시군구 11) 안에 있다" 또는 "법정동 1111010100(종로구 청운동) 근처다"라고 사전 확신하는 경우, 본 라이브러리가 `sig_cd` 또는 `bjd_cd` 접두사를 hint로 받아 다음을 동시에 달성한다.

1. **검색 범위 축소**: 전국 6.4M행에서 서울 100만대로, 청운동 ~수천행으로 후보 축소.
2. **인덱스 활용**: 기존 `idx_*_resolve`(시도/시군구/도로명 기반 btree)나 신규 `idx_mv_*_sig_cd`/`idx_mv_*_bjd_cd` partial/multi-column 인덱스로 plan 단순화.
3. **외부 fallback 비용 절감**: 좌표가 명백히 한 시도 안에 있으면 fuzzy/keyword 검색 backoff 시점에 외부 API call 횟수 감소.

본 task는 T-047 query benchmark와 함께 측정해 hint가 실제로 p95/p99를 줄이는지 검증한 뒤, 효과가 있으면 v2 API 입력 필드와 라이브러리 함수에 노출한다.

## hint 종류와 의미

| hint | 길이 | 예시 | 의미 |
|------|------|------|------|
| `sig_cd` | 5 | `11`(서울특별시 — 5자리 채우면 `11000`/`11???`. 시도 단위는 `sig_cd LIKE '11%'`) | 시도 또는 시군구 단위 한정 |
| `bjd_cd` | 10 | `1111010100` | 법정동까지 한정 |
| `emd_cd` | 8 | `11110101` | 읍면동(법정동 8자리) — 시군구+법정동 prefix |
| `bbox` | (minx, miny, maxx, maxy) EPSG:4326 | `(126.95, 37.55, 127.05, 37.6)` | 좌표 박스 한정 |

길이 별 동작:

- `sig_cd=11`(시도 prefix): `WHERE sig_cd LIKE '11%'`.
- `sig_cd=11680`(강남구 5자리): `WHERE sig_cd = '11680'`.
- `bjd_cd=1111010100`: `WHERE bjd_cd = '1111010100'`.
- `bjd_cd=11110101`: `WHERE bjd_cd LIKE '11110101%'`.

`bbox`는 좌표 reverse에서 spatial 범위 한정에 직접 활용.

## 후보 표면

### v2 API (T-052와 연결)

```python
class GeocodeV2Input(FrozenModel):
    query: str | None = None
    road_address: str | None = None
    jibun_address: str | None = None
    keyword: str | None = None
    sig_cd: str | None = None              # T-057
    bjd_cd: str | None = None              # T-057
    bbox: tuple[float, float, float, float] | None = None  # T-057
    limit: int = 10
    fallback: Literal["none","api"] = "none"
```

### 라이브러리

```python
class AsyncAddressClient:
    async def geocode_v2(
        self, *, query: str | None = None, sig_cd: str | None = None, bjd_cd: str | None = None,
        bbox: tuple[float, float, float, float] | None = None, ...
    ) -> GeocodeV2Response: ...

    async def reverse_v2(
        self, lon: float, lat: float, *, sig_cd: str | None = None, ...
    ) -> ReverseV2Response: ...

    async def search_v2(
        self, *, query: str, sig_cd: str | None = None, bjd_cd: str | None = None, ...
    ) -> SearchV2Response: ...
```

v1 API는 호환성 유지를 위해 hint를 받지 않는다(별도 변경 없음).

## 구현 sketch

### 1. parser에서 hint 추출

호출자가 명시 hint를 보내지 않아도, query 문자열 안에 시도/시군구가 명확히 있으면 parser가 hint를 자동 생성한다.

```python
def derive_region_hint(parsed: ParsedAddress) -> RegionHint:
    if parsed.sig_cd:
        return RegionHint(sig_cd=parsed.sig_cd)
    if parsed.ctp_kor_nm:
        sido = lookup_sido_code(parsed.ctp_kor_nm)
        if sido:
            return RegionHint(sig_cd=sido[:2])  # 시도 prefix
    return RegionHint()  # empty
```

호출자가 보낸 hint와 parser hint가 다르면, 호출자 hint 우선(명시적 입력 신뢰).

### 2. SQL에서 hint 적용

#### geocode (도로명 exact)

```sql
WITH candidates AS (
  SELECT *
  FROM mv_geocode_target
  WHERE rncode_full = :rncode_full
    AND buld_se_cd = :buld_se_cd
    AND buld_mnnm = :buld_mnnm
    AND buld_slno = :buld_slno
    AND ( :sig_cd_filter IS NULL OR sig_cd = :sig_cd_filter )  -- T-057 hint
    AND ( :bjd_cd_prefix IS NULL OR bjd_cd LIKE :bjd_cd_prefix )  -- T-057 hint
)
SELECT ... FROM candidates LIMIT :limit;
```

PostgreSQL planner가 `sig_cd`/`bjd_cd` 인덱스를 활용하도록 `idx_mv_geocode_target_sig` (`sig_cd, rncode_full`) 같은 multi-column 인덱스를 검토.

#### fuzzy geocode (`pg_trgm`)

```sql
SELECT *,
       similarity(buld_nm, :query) AS sim
FROM mv_geocode_target
WHERE
  ( :sig_cd_filter IS NULL OR sig_cd = :sig_cd_filter )
  AND buld_nm % :query
ORDER BY sim DESC
LIMIT :limit;
```

hint가 있으면 `pg_trgm` GIN scan 후 hint filter, 또는 hint partial index (`CREATE INDEX ... WHERE sig_cd = '11'`)를 고려. partial은 17개 시도 × 8 partial = 136개 인덱스라 관리 cost 크므로 보수적으로.

#### reverse nearest

```sql
WITH target_pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179) AS geom)
SELECT *
FROM mv_geocode_target m, target_pt p
WHERE
  ( :sig_cd_filter IS NULL OR m.sig_cd = :sig_cd_filter )
  AND ST_DWithin(m.pt_5179, p.geom, :radius_m)
ORDER BY m.pt_5179 <-> p.geom
LIMIT :limit;
```

hint가 있으면 spatial GIST scan 결과를 hint로 사전 cut.

### 3. region hint 유도 helper

```python
@dataclass(frozen=True, slots=True)
class RegionHint:
    sig_cd: str | None = None
    bjd_cd: str | None = None
    bbox: tuple[float, float, float, float] | None = None

    def to_filter(self) -> dict[str, str | None]:
        return {
            "sig_cd_filter": self.sig_cd if self.sig_cd and len(self.sig_cd) == 5 else None,
            "sig_cd_prefix": f"{self.sig_cd}%" if self.sig_cd and len(self.sig_cd) < 5 else None,
            "bjd_cd_filter": self.bjd_cd if self.bjd_cd and len(self.bjd_cd) == 10 else None,
            "bjd_cd_prefix": f"{self.bjd_cd}%" if self.bjd_cd and len(self.bjd_cd) < 10 else None,
        }
```

## benchmark 설계

T-047 query benchmark corpus에 다음 case를 추가:

| case_id | query | no-hint | with hint (sig_cd=11) | with hint (bjd_cd=1111010100) |
|---------|-------|---------|------------------------|-------------------------------|
| Q1_road_exact | "자하문로 94" | baseline | sig_cd=11 | bjd_cd=1111010100 |
| Q2_jibun_exact | "청운동 1-1" | baseline | sig_cd=11 | bjd_cd=1111010100 |
| Q3_fuzzy | "청운빌라" | baseline | sig_cd=11 | - |
| Q4_search | "효자" | baseline | sig_cd=11 | - |
| Q5_reverse_nearest | (126.97, 37.58) | baseline | sig_cd=11 | - |

측정 항목:

- p50/p95/p99 latency (no-hint vs hint).
- `EXPLAIN ANALYZE` plan 비교 (index 사용 여부).
- Buffer hit ratio.
- 결과 row count 동일성 (hint가 잘못된 결과를 만들지 않는지).

목표: hint 적용 시 p95이 baseline 대비 50% 이상 단축되는 case 식별.

## 인덱스 후보

현재 `mv_geocode_target` 인덱스:

- `idx_mv_geocode_target_pk` (bd_mgt_sn)
- `idx_mv_road` (rncode_full, buld_mnnm, buld_slno, buld_se_cd)
- `idx_mv_jibun` (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)
- `idx_mv_rn_trgm` (rn_norm gin_trgm_ops)
- `idx_mv_buld_nm_trgm` (buld_nm gin_trgm_ops)
- `idx_mv_geom5179` (pt_5179 GIST)
- `idx_mv_geom4326` (pt_4326 GIST)
- `idx_mv_pt_source` (pt_source)

T-057 후보 추가:

- `idx_mv_sig_road` (sig_cd, rncode_full, buld_se_cd, buld_mnnm, buld_slno) — sig_cd hint + 도로명 exact 가속.
- `idx_mv_sig_bjd` (sig_cd, bjd_cd) — sig_cd hint + bjd_cd 결합.
- (선택) sig_cd partial 인덱스 — 측정 후 결정.

추가 인덱스는 build/refresh 시간과 디스크 영향이 있으므로 T-047 benchmark로 ROI 측정 후 결정.

## query rewrite 전략

PostgreSQL planner가 hint를 활용하지 못하는 경우 다음을 검토:

1. CTE materialize/inline 옵션.
2. `set_join_collapse_limit`, `set_from_collapse_limit` 조정.
3. CASE 표현 대신 dynamic SQL 생성(hint 유무에 따라 `WHERE` 절 다른 형태).
4. SQL view 분리: `v_mv_geocode_seoul`, `v_mv_geocode_busan` 같은 시도별 view → hint = view selection.

옵션 4는 관리 비용 ↑. ROI 측정으로 도입 여부 결정.

## 검증 기준

- benchmark 결과 표 docs에 inline (no-hint vs hint p95/p99).
- 같은 query에 대해 hint 유/무 결과 row가 동일(다른 row가 나오면 hint가 잘못된 결과 생성).
- v2 API 단위 테스트: hint 입력 → 응답 candidate가 hint 범위 안에 있음.
- `EXPLAIN ANALYZE` plan에서 hint 인덱스 사용 확인.

## 남은 위험

- hint가 잘못된 값(존재하지 않는 sig_cd, 길이 오류)일 때 조용히 무시할지 명시 에러 반환할지 정책 필요. → 기본 명시 에러 + `?strict_hint=false`로 무시 옵션.
- partial 인덱스 17개 × 5종 = 85개는 관리 cost 큼. multi-column 인덱스 1~2개로 시작.
- bbox hint는 좌표계 혼동 위험. 입력은 EPSG:4326 lon/lat 표준 명시 + 자동 EPSG:5179 변환.
- region hint와 외부 fallback(vworld/kakao/naver) 조합 시 일관성 필요. 외부 fallback이 hint를 지원하지 않으면 hint 무시 + warning log.

## 관련 ADR/Task

- T-047: hint vs no-hint 성능 측정.
- T-052: v2 API 입력 필드(`sig_cd`, `bjd_cd`, `bbox`).
- T-053: `/admin/performance`에서 hint 효과 시각화.
