# T-169 v2 enum 정직화

날짜: 2026-06-16  
담당: Agent A / Codex

## 요약

v2 후보 enum을 현재 producer와 후속 확장 방향에 맞게 정리했다. `match_kind`에서는 실제 후보 의미가 없는 `postal`, `category`를 제거하고, typed 상세주소와 POI 후보를 위한 `detail`, `poi`를 추가했다. 장소 검색 결과는 더 이상 `keyword` 후보로 표시하지 않고 `poi` 후보로 변환한다.

국가지점번호 후보의 좌표는 EPSG:5179 10m cell 중심 계산값이므로 `point_precision="approximate"` 대신 `grid_cell`로 표현한다. `V2Source`에서는 별도 provider가 아닌 v1 내부 캐시 값을 제거하고, v1 `source="cache"`가 들어오면 v2에서는 `local`로 접는다.

## enum 계약

| enum | 값 | 생산/의미 |
|------|----|-----------|
| `V2MatchKind` | `road`, `parcel` | v1 geocode/reverse/search 주소 후보 |
| `V2MatchKind` | `keyword` | 키워드 입력 기반 후보. 장소 실체는 `poi`로 표현 |
| `V2MatchKind` | `region` | 행정구역/도형 후보 |
| `V2MatchKind` | `sppn` | 계산된 국가지점번호 후보 |
| `V2MatchKind` | `detail` | 상세주소 typed candidate용 예약 값 |
| `V2MatchKind` | `poi` | 장소/POI 후보 |
| `V2PointPrecision` | `exact`, `interpolated`, `centroid`, `approximate` | 기존 좌표 정밀도 계층 |
| `V2PointPrecision` | `grid_cell` | 국가지점번호 10m cell 계산 좌표 |
| `V2Source` | `local`, `vworld`, `juso` | 현재 v2가 공개하는 provider/source |

제거한 값은 다음과 같다.

- `match_kind="postal"`: 우편번호 조회는 별도 응답 모델이고 현재 v2 후보 producer가 없다.
- `match_kind="category"`: category 입력은 검색 hint이며 후보 실체는 장소이므로 `poi`로 표현한다.
- `source="cache"`: 내부 캐시 경유 여부는 provider/source가 아니다. 필요하면 metadata나 관측 지표로 별도 노출한다.

## ADR-055와의 관계

ADR-055는 C11 좌표 세부 출처를 `pt_source` enum에 섞지 않고 v2 `metadata.pt_source`/`metadata.coord_source_detail`로 둔다. T-169도 이 결정을 유지한다. 이번 PR은 SPPN의 `grid_cell`처럼 이미 안정 producer가 있는 precision만 public enum으로 올리고, C11/상세주소/POI의 세부 좌표 유형은 아직 `point_precision` 값으로 늘리지 않는다.

## 검증

- `tests/unit/test_v2_api.py`
  - `postal`, `category`, `cache` dead enum 거절
  - `detail`, `poi`, `grid_cell` schema 수용
  - `place` 검색 결과를 `match_kind="poi"`로 변환
  - SPPN geocode/reverse 후보를 `point_precision="grid_cell"`로 변환
- `openapi.json`과 `kor-travel-geo-ui/types/api.gen.ts`를 재생성한다.
