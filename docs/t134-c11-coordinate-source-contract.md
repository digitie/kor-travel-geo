# T-134 C11 좌표 출처 노출 계약

작성일: 2026-06-16

상태: **accepted**

관련: T-118, T-123, T-125, T-131, T-132, T-133, T-137, T-119, T-105, T-169, T-219, ADR-003, ADR-051, ADR-053, ADR-054, ADR-055

## 목적

T-125 이후 C11 `도로명주소 건물 도형` 출입구 후보는 active serving에 승격되지 않았다. T-132의 guarded 후보는 correctness hard block이 없었지만 100m 초과 이동 warning이 남았고, T-133 shadow serving 리허설은 rollback은 통과했지만 SQL/REST p95 성능 gate가 실패했다.

따라서 T-134는 코드를 바꾸지 않고, C11이 나중에 다시 검토될 때 v1/v2 응답에서 좌표 출처를 어떻게 표현할지 먼저 고정한다. 이 문서는 OpenAPI/UI 타입 영향과 테스트 계획까지 적되, DTO/MV/API 구현은 별도 PR로 미룬다.

## 결론

1. `pt_source`는 계속 coarse enum으로 둔다. 값은 `entrance`, `centroid`만 허용하고 `c11_bundle_guarded`, `locsum_entrc`, `roadaddr_entrc` 같은 세부 원천명을 넣지 않는다.
2. 세부 출처는 `coord_source_detail`로만 표현한다. C11 guarded 후보는 `coord_source_detail="c11_bundle_guarded"`를 사용한다.
3. v1 VWorld 호환 표면에는 최상위 또는 `result` 자체 필드를 추가하지 않는다. 노출이 필요하면 `response.x_extension.pt_source`와 `response.x_extension.coord_source_detail`만 사용한다.
4. v2는 `CandidateV2.point_precision`으로 큰 정밀도 계층을 표현하고, 세부 출처는 `CandidateV2.metadata.pt_source`와 `CandidateV2.metadata.coord_source_detail`에 둔다. 안정 public field 승격이나 enum 확장은 T-105/T-169에서 별도 결정한다.
5. 현재 코드에는 `GeocodeExtension.pt_source`나 `coord_source_detail`이 없으므로 이번 PR에서 OpenAPI/typegen을 바꾸지 않는다. 구현이 필요해지는 시점은 T-137에서 C11 gate가 통과하고 T-119를 사용자 승인으로 재개할 때다.

## 용어

| 이름 | 의미 | 안정성 |
|------|------|--------|
| `pt_source` | 좌표의 큰 분류. `entrance`는 출입구급 좌표, `centroid`는 건물 중심 fallback이다. | 안정 enum |
| `coord_source_detail` | 실제 좌표 산출 경로. 예: `locsum_entrc`, `roadaddr_entrc_same_month`, `navi_buld_centroid`, `c11_bundle_guarded`. | 확장 가능한 문자열 |
| `point_precision` | v2 후보 좌표 정밀도. 현재 enum은 `exact`, `interpolated`, `centroid`, `approximate`, `grid_cell`이다. | 안정 enum, T-169에서 국가지점번호 `grid_cell`만 확정 |

`coord_source_detail` 값은 PostgreSQL identifier와 비슷한 소문자 snake_case로 둔다. provider 원문, 파일명, 기준월은 여기에 직접 넣지 않고 별도 metadata나 artifact에 둔다.

## `pt_source` 값 결정

`pt_source`는 세부 원천 추적용이 아니라 조회 ranking과 대략적인 좌표 품질을 나타내는 coarse field다. 새 source를 추가할 때 enum을 늘리면 다음 문제가 생긴다.

- `ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END` 같은 hot path가 새 값을 어떻게 처리할지 불명확해진다.
- v1 소비자가 `x_extension` 아래 값만 보더라도 `pt_source` enum 확대에 의존할 수 있다.
- Admin UI와 benchmark 집계가 source별 통계를 세부 원천과 coarse precision을 섞어 해석하게 된다.

따라서 실제 좌표가 출입구급이면 coarse `pt_source='entrance'`, 건물 중심 fallback이면 `pt_source='centroid'`다. C11이 나중에 active serving에 들어가더라도 `pt_source='c11_bundle_guarded'` 같은 값은 만들지 않는다.

T-133 shadow 리허설은 active serving promotion이 아니었으므로 public 호환성을 보수적으로 보려고 `pt_source`를 기존 값 그대로 유지했다. 이것은 리허설 구현 선택이지 future active serving 계약이 아니다. T-137에서 C11을 다시 go로 판정하고 T-119 구현이 승인되면, 실제 serving MV는 좌표 의미에 맞게 `pt_source`와 `coord_source_detail`을 함께 산출해야 한다.

## v1 계약

REST v1은 ADR-003/ADR-053의 VWorld envelope를 유지한다.

금지:

- `response.result.pt_source` 추가
- `response.result.coord_source_detail` 추가
- `response` 최상위에 `pt_source`, `coord_source_detail` 추가
- `service`, `input`, `refined`, `result`의 VWorld 호환 key 의미 변경

허용:

```json
{
  "response": {
    "status": "OK",
    "result": {
      "crs": "EPSG:4326",
      "point": { "x": 127.0, "y": 37.0 }
    },
    "x_extension": {
      "source": "local",
      "confidence": 0.94,
      "pt_source": "entrance",
      "coord_source_detail": "c11_bundle_guarded"
    }
  }
}
```

v1 reverse는 결과가 여러 개라 `response.x_extension.coord_source_detail` 하나로는 후보별 출처를 안정적으로 표현할 수 없다. 따라서 v1 reverse에는 C11 세부 출처를 새로 노출하지 않고, 후보별 metadata가 필요한 사용자는 v2 reverse를 사용한다. v1 reverse의 기존 `x_extension.sppn_makarea` 보조 문맥은 그대로 유지한다.

## v2 계약

v2는 후보 목록 API이므로 후보별 metadata를 사용할 수 있다.

| `pt_source` | 기본 `point_precision` | `metadata.coord_source_detail` 예 |
|-------------|------------------------|-----------------------------------|
| `entrance` | `exact` | `locsum_entrc`, `roadaddr_entrc_same_month`, `c11_bundle_guarded` |
| `centroid` | `centroid` | `navi_buld_centroid` |
| 없음 | `null` 또는 기존 특수값 | 국가지점번호 등 별도 흐름 |

국가지점번호는 C11과 다른 좌표 계열이다. T-169에서 v2 국가지점번호 후보는 `point_precision="grid_cell"`로 정정했다. T-134는 C11 때문에 `point_precision` enum을 더 넓게 늘리거나 C11 세부 출처를 stable field로 승격하지 않는다.

v2에서 안정 public field를 추가할 후보는 다음과 같다.

- `CandidateV2.point_source`: `pt_source`를 metadata 밖으로 승격
- `CandidateV2.coordinate_source_detail`: `coord_source_detail`을 metadata 밖으로 승격
- `V2PointPrecision` enum 확장: T-169에서 `grid_cell`만 확정. `entrance`, `detail`, `poi` 같은 세부 좌표 유형은 아직 precision enum으로 승격하지 않는다.

이 후보는 T-105 v2 재audit과 T-169 enum 정직화에서 API 전체와 함께 재검토한다. T-134에서는 `metadata`를 임시 안정 표면으로 둔다.

## OpenAPI와 UI 영향

이번 PR은 코드와 OpenAPI를 바꾸지 않는다.

향후 구현 PR에서 `GeocodeExtension`에 optional field를 추가하면 다음 작업이 필요하다.

1. `scripts/export_openapi.py` 실행.
2. `kor-travel-geo-ui`에서 `npm run gen:types`.
3. v1 geocode HTTP 테스트에서 `pt_source`와 `coord_source_detail`이 `response.x_extension` 아래에만 있는지 확인.
4. `/debug/geocode` JSON 표시가 새 필드를 보여 주는지 확인. 별도 배지를 만들 경우 `coord_source_detail`을 사용자 친화 label로 매핑한다.
5. v1 reverse는 이번 계약상 C11 detail을 노출하지 않는다는 회귀 테스트를 둔다.

`CandidateV2.metadata`만 사용하면 OpenAPI schema 변화는 작다. 하지만 `point_precision` 매핑을 바꾸면 응답 golden test와 UI 표시 테스트를 함께 갱신한다.

## 테스트 계획

구현 PR이 생기면 다음 테스트를 추가한다.

| 영역 | 테스트 |
|------|--------|
| DTO | `GeocodeExtension(pt_source="entrance", coord_source_detail="c11_bundle_guarded")` 직렬화가 `x_extension` 내부 key만 만든다. |
| v1 geocode | HTTP envelope에서 `response.result`에는 새 key가 없고 `response.x_extension`에만 두 field가 있다. |
| v1 simple | `simple=true`에서도 VWorld 생략 규칙은 유지하고, `x_extension` 유지 여부는 ADR-053과 동일하게 검증한다. |
| v1 reverse | 후보별 C11 detail을 v1 reverse에 노출하지 않는다는 계약을 고정한다. |
| core | `AddressLookup.pt_source`와 future `coord_source_detail`이 confidence와 extension으로 분리 매핑된다. |
| infra | `mv_geocode_target` 또는 shadow projection이 `pt_source` coarse enum과 `coord_source_detail` detail을 함께 산출한다. |
| v2 geocode/reverse | `CandidateV2.point_precision`, `metadata.pt_source`, `metadata.coord_source_detail` 매핑을 확인한다. |
| OpenAPI/typegen | optional field 추가 후 `openapi --check`, UI `gen:types`, `type-check`가 통과한다. |
| live gate | T-137/T-119에서 C11 flag off/on response hash와 detail field 분포를 artifact로 남긴다. |

## T-137 입력

T-137은 C11 최종 gate에서 다음 결론을 사용한다.

- C11이 계속 no-go면 구현하지 않는다. 문서 계약만 유지한다.
- C11이 조건부 go가 되더라도 `pt_source` enum 확장은 금지한다.
- active serving promotion 전에는 `coord_source_detail`이 OpenAPI/UI/typegen/test 계획과 함께 구현되어야 한다.
- T-119는 ADR-051 accepted 전환과 사용자 명시 승인 없이는 착수하지 않는다.
