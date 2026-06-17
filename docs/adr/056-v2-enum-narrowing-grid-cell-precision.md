# ADR-056: v2 후보 enum은 producer 의미 기준으로 좁히고 국가지점번호는 `grid_cell` 정밀도로 표현한다

- 상태: accepted
- 날짜: 2026-06-16
- 결정자: codex
- 관련: T-169, T-105, T-134, T-166, T-167, T-168, ADR-038, ADR-054, ADR-055

## 컨텍스트

T-052에서 만든 v2 candidate schema는 외부 API 스타일을 참고하며 `postal`, `category`, `cache` 같은 확장 후보 값을 넓게 열어 두었다. 이후 T-166~T-168에서 국가지점번호가 first-class 후보가 됐고, T-134/ADR-055는 C11 세부 좌표 출처를 public enum에 바로 섞지 않기로 했다. T-169에서는 실제 producer 의미와 향후 typed 후보 방향을 기준으로 v2 enum을 다시 좁혀야 했다.

## 결정

1. `V2MatchKind`는 `road`, `parcel`, `keyword`, `region`, `sppn`, `detail`, `poi`로 둔다.
2. `postal`은 제거한다. 우편번호 조회는 별도 응답 표면이고 현재 v2 candidate producer가 없다.
3. `category`는 제거한다. category는 검색 입력 hint이고 후보 실체는 장소/POI이므로 `poi`로 표현한다.
4. `SearchResultItem.type="place"`는 v2에서 `match_kind="poi"`로 변환한다.
5. `V2PointPrecision`에는 `grid_cell`을 추가한다. 국가지점번호 geocode/reverse 후보는 10m cell 중심 계산 좌표이므로 `approximate`가 아니라 `grid_cell`을 사용한다.
6. `V2Source`는 `local`, `vworld`, `juso`로 좁힌다. v1 내부 `source="cache"`는 provider/source가 아니므로 v2에서는 `local`로 접는다.
7. ADR-055의 C11 계약은 유지한다. `entrance`, `detail`, `poi` 같은 세부 좌표 유형은 이번 PR에서 `point_precision` enum으로 승격하지 않고 metadata/후속 T-105 재audit 대상에 남긴다.

## 근거

- v2 enum은 클라이언트가 분기하는 공개 계약이므로 "나중에 쓸 수도 있는 값"보다 현재 의미가 설명 가능한 값만 둬야 한다.
- `category`와 `cache`는 후보의 본질이나 provider가 아니라 입력/처리 경로다. public enum에 두면 UI와 SDK가 잘못된 분기를 만들 가능성이 높다.
- 국가지점번호는 주소 대표점이나 면 centroid가 아니라 10m grid cell 중심이다. `grid_cell`이 `approximate`보다 더 정확한 의미를 전달한다.
- C11은 T-137에서 validation-only로 고정됐으므로 지금 public precision/source field를 늘릴 이유가 없다.

## 결과

- OpenAPI와 frontend 생성 타입에서 `V2MatchKind`, `V2PointPrecision`, `V2Source` enum이 갱신된다.
- SPPN v2 후보는 forward/reverse 모두 `point_precision="grid_cell"`을 낸다.
- 장소 후보는 `keyword`가 아니라 `poi`로 노출된다.

## 후속

- T-105 v2 재audit에서 error model, pagination, bbox/include_geometry, candidate source field 승격 여부를 계속 검토한다.
- 상세주소 typed candidate를 실제 구현할 때 `match_kind="detail"`의 producer, fallback 좌표 정책, metadata 계약을 별도 테스트로 고정한다.
