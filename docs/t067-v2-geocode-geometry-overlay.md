# T-067: v2 geocode point+geometry overlay와 디버그 UI 지도 보강

## 상태

- 상태: 완료
- 날짜: 2026-05-30
- 대상 브랜치: `codex/t067-v2-point-geometry-overlay`
- 사용자 재확인: "`포인트 + 영역 리턴임. 헷갈리지 말 것`" — 기존 대표점(`point`)을 도형으로 대체하지 않고, 후보에 도형(`geometry`)을 추가한다.

## 목적

디버그 UI에서 주소 입력 결과를 좌표 하나로만 보는 한계를 줄인다. 사용자가 상위 주소, 도로명, 건물 주소를 입력했을 때 같은 `/v2/geocode` 후보 응답 안에서 대표점과 공간 범위를 함께 보고 판단할 수 있게 한다.

대표 시나리오는 다음 3가지다.

| 입력 | 유지되는 `point` | 추가되는 `geometry` |
|------|------------------|---------------------|
| `성복동` | 행정구역 polygon의 대표점 | `tl_scco_emd` 행정구역 `MultiPolygon` |
| `성복1로` | 도로 관리선의 대표점 | `tl_sprd_manage` 도로 `MultiLineString` |
| `성복1로 35` | 기존 geocode 대표점 또는 출입구점 | `tl_spbd_buld_polygon` 건물 `MultiPolygon` |

## API 변경

`GeocodeV2Input`에 `include_geometry: bool = false`를 추가했다. 기본값은 기존 응답 크기와 동작을 유지하기 위해 `false`다. 디버그 UI는 공간 비교가 목적이므로 기본으로 `true`를 보낸다.

`CandidateV2`에는 다음 필드를 추가했다. 응답 의미는 `point + geometry`다. `geometry`가 있더라도 `point`는 사라지거나 도형 중심점으로 덮어쓰이지 않는다.

- `geometry`: `GeometryV2 | null`
- `GeometryV2.kind`: `building`, `region`, `road`
- `GeometryV2.crs`: `EPSG:4326`
- `GeometryV2.geojson`: PostGIS에서 `ST_AsGeoJSON(..., 6, 1)`로 만든 GeoJSON geometry 객체
- `GeometryV2.source_table`: `tl_spbd_buld_polygon`, `tl_scco_*`, `tl_sprd_manage`

`bbox`는 `include_geometry=true`일 때 후보 도형의 EPSG:4326 범위로 채운다. 클라이언트는 `bbox`와 `point`를 함께 포함하도록 지도 viewport를 잡아야 한다. 건물 출입구점은 건물 polygon 외부 도로 쪽에 있을 수 있으므로 `bbox`만으로 지도를 맞추면 `point` marker가 화면 밖으로 밀릴 수 있다.

## 조회 규칙

### 건물 주소

일반 도로명/지번 geocode가 성공하면 기존 v1 geocode 결과를 v2 후보로 변환한 뒤 도형을 보강한다.

1. `bd_mgt_sn` 직접 lookup을 먼저 시도한다.
2. 도로명주소 정본 `bd_mgt_sn`과 SHP 건물 polygon `bd_mgt_sn`이 직접 일치하지 않는 경우를 위해 `rncode_full + bjd_cd + 건물번호` natural key lookup도 시도한다.
3. `point`는 기존 geocode 결과 그대로 둔다.
4. `geometry.kind="building"`과 `bbox`만 추가한다.

### 도로명만 입력

상세 건물번호가 없어 기존 geocode가 실패하거나 `NOT_FOUND`인 경우, district 후보로 넘기기 전에 `tl_sprd_manage` 도로 관리선 후보를 먼저 찾는다.

도로명 후보는 다음 순서로 점수화한다.

- 도로명 정규화 exact
- 시군구 포함 full title exact
- suffix exact
- contains fallback

반환 후보의 `match_kind`는 `road`, `point_precision`은 `centroid`, `geometry.kind`는 `road`다.

### 행정구역만 입력

상세 주소가 없고 도로명 후보도 없으면 기존 T-064 흐름처럼 `search(type="district")` 후보로 승격한다. `include_geometry=true`이면 후보의 `sig_cd`/`bjd_cd`를 기준으로 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li` 중 하나를 찾아 `geometry.kind="region"`으로 붙인다.

## 디버그 UI 변경

- `/debug/geocode`는 기본으로 `include_geometry=true`를 보낸다. 필요하면 체크박스로 끌 수 있다.
- `/debug/geocode`와 `/debug/reverse` 모두 응답 JSON을 입력 패널 아래로 옮겼다.
- 지도 패널은 오른쪽의 큰 영역으로 분리했다.
- `CoordinateMap`은 기존 marker를 유지하면서 GeoJSON overlay를 추가한다.
  - polygon: fill + outline
  - line: 두꺼운 blue line
  - point: circle layer
- 지도 viewport는 `bbox`와 `point`를 함께 포함하도록 맞춘다.

## 실제 DB 확인

Docker PostGIS `kraddr-geo-t027-final-db-1` (`127.0.0.1:15434`, `kraddr_geo`)에서 `AsyncAddressClient.geocode(..., include_geometry=True)`로 확인했다.

| 입력 | 상태 | 첫 후보 | point | geometry |
|------|------|---------|-------|----------|
| `성복동` | `OK` | `match_kind=region` | `(127.05932949615165, 37.319558336433374)` | `region`, `MultiPolygon` |
| `성복1로` | `OK` | `match_kind=road` | `(127.0610437873178, 37.32091740399021)` | `road`, `MultiLineString` |
| `성복1로 35` | `OK` | `match_kind=road` | `(127.07430262108355, 37.31347098160811)` | `building`, `MultiPolygon` |

`성복1로 35`는 기존 geocode point를 유지하면서 건물 polygon을 추가한다. 이 둘은 같은 좌표가 아니며, UI는 둘 다 보이도록 범위를 잡는다.

## 검증

- `pytest tests/unit/test_v2_api.py -q` → `10 passed`
- `ruff check ...` → 통과
- `mypy --strict src/kraddr/geo/dto/v2.py src/kraddr/geo/core/protocols.py src/kraddr/geo/core/v2.py src/kraddr/geo/infra/geometry_repo.py src/kraddr/geo/client.py src/kraddr/geo/api/routers/v2.py` → 통과
- `npm run gen:types` → OpenAPI/TypeScript 타입 갱신
- `npm run lint` → 통과
- `npm run type-check` → 통과
- `npm run test` → `34 passed`

## 남은 위험

- GeoJSON payload는 polygon 크기에 비례해 커진다. 운영 기본값은 `include_geometry=false`로 유지하고, 디버그 UI나 명시 호출에서만 켠다.
- 현재 geometry는 단순화하지 않는다. 대형 행정구역 polygon의 응답 크기와 렌더링 비용이 문제가 되면 `simplify_tolerance_m` 같은 별도 옵션을 후속으로 검토한다.
- reverse geocode의 도형 반환은 이번 범위에서 추가하지 않았다. 화면 레이아웃만 조정했고, reverse 후보 도형 옵션은 별도 요구가 있을 때 API 설계를 확장한다.
