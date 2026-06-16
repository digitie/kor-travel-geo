# v2 Reverse

## 요약

`POST /v2/reverse`는 좌표 주변의 주소 후보를 provider-neutral candidate 목록으로 반환한다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `lon` | float | 필수 | 경도 |
| `lat` | float | 필수 | 위도 |
| `crs` | string | `EPSG:4326` | 입력 좌표계 |
| `include_region` | boolean | `true` | region 보강 필드 포함 여부 |
| `include_zipcode` | boolean | `true` | 우편번호 보강 여부 |
| `radius_m` | integer | `200` | 검색 반경(미터, 단위 suffix 규약 — ADR-060 §6) |
| `sig_cd` | string | 없음 | 시도/시군구 hint |
| `bjd_cd` | string | 없음 | 법정동 hint |
| `include_geometry` | boolean | `false` | 후보에 도형(`geometry`/`bbox`) 포함 여부. geocode/search와 동일한 opt-in(ADR-060 §5, ADR-059) |

`include_geometry`는 geocode/search와 대칭으로 받는다. 후보가 도형 조회 key를 가질 때만 채워진다 — 현재 reverse local 후보는 도로명/지번(`match_kind="road"`/`"parcel"`)이고 건물 도형 key(`bd_mgt_sn` 또는 `rncode_full`+`bjd_cd`+상세번호)를 함께 싣지 않으므로 `geometry`는 보통 `null`이다. 점 기반 건물 도형 조회는 후속 확장으로 남긴다.

## 출력

`candidates[]`는 도로명/지번 후보를 함께 담는다. 입력 좌표가 한국 SPPN 지원 envelope 안에 있으면 계산된 국가지점번호를 `match_kind="sppn"` 후보로 함께 반환한다. 표기 의무지역 polygon에 포함되면 같은 후보 metadata에 `makarea` 문맥도 붙는다. 각 후보는 `match_kind`, `address`, `point`, `region`, `source`, `distance_m`, `confidence`를 포함할 수 있다.

- `distance_m`: 입력 좌표와 후보 좌표 사이의 거리다. metadata에도 같은 값을 남기지만, 클라이언트는 정식 필드인 `distance_m`을 우선 사용한다.
- `confidence`: `1 - distance_m / radius_m`로 계산한 반경 내 근접도다. 값은 0~1이고, geocode/search confidence와 직접 비교하지 않는다.
- `point_precision`: 좌표 정밀도 enum이다. 현재 reverse local 주소 후보는 upstream v1 결과가 `pt_source`를 직접 노출하지 않아 보통 `null`이며, 국가지점번호 후보는 10m cell 계산 좌표이므로 `grid_cell`이다.
- `match_kind="sppn"`: 주소가 아니라 계산된 국가지점번호 또는 표기 의무지역 문맥이다. 이 후보는 `address`가 없을 수 있고, `metadata.national_point_number`를 담는다. 표기 의무지역 polygon에 포함되면 `sig_cd`, `makarea_id`, `makarea_nm`, `source_yyyymm`, `area_m2` 같은 원천 정보도 함께 담는다.

## 예시

```bash
curl -X POST "http://localhost:12501/v2/reverse" \
  -H "Content-Type: application/json" \
  -d '{"lon":127.036,"lat":37.501,"radius_m":200}'
```

```python
async with AsyncAddressClient() as client:
    response = await client.reverse(127.036, 37.501, radius_m=200)
```

## 구현 메모

현재 v2 reverse는 local DB를 사용한다. Kakao의 주소/행정구역 reverse 분리, Kakao/Naver의 distance first-class 표현, Naver의 reverse 구성요소 표현은 schema 설계 참고자료일 뿐이며, live adapter를 추가하지 않는다.
