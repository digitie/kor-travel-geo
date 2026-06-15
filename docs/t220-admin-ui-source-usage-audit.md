# T-220 — 실제 활용 파일 ↔ Admin UI 정합성 감사

작성일: 2026-06-16
담당: Claude (Agent B)
관련: T-209, T-216, T-128(ADR-054), `docs/optional-source-usage-decision.md`, 후속 구현 T-221/T-224
방법: 다중 에이전트 grounding 감사(UI 라벨링 / 백엔드 API·카탈로그 / ADR-054 ground truth), 모든 주장 `file:line` 대조.

## 결론 (감사 verdict)

**`/admin/source-files`는 현재 source의 실제 serving 활용도를 오해시킬 수 있다 (NEEDS FIX → T-221).**

핵심 원인은 **백엔드 데이터 gap**이다 — UI 버그가 아니라 카탈로그/DTO에 "serving 활용 분류" 신호 자체가 없다:

1. **카탈로그 `role`이 정적이다.** `GET /v1/admin/source-file-categories`는 `role = category.default_role`을 그대로 반환하고 **active match set과 join하지 않는다**(`api/routers/admin.py:259-272`). DTO docstring도 "role/default_role are UI defaults; authoritative role lives on `ops.source_match_set_items.role`"라고 명시(`dto/source.py:78-80`). 즉 카탈로그 응답에는 "active serving 포함 여부"를 그릴 데이터가 없다.
2. **역할 배지가 전부 녹색이다.** `sourceRoleLabels`(`lib/source-files.ts:62-67`)는 4역할을 `필수 구성/권장 구성/검증 선택/보강 후보`로 매핑하고, `StatusBadge`→`severityClass`(`lib/consistency.ts:3-8`)는 ERROR/WARN/FAILED 외 모든 문자열을 `ok`(녹색, `globals.css:636`)로 렌더한다 → 검증 전용·보강 후보 optional이 필수 serving core와 **시각적으로 구분되지 않는다**.
3. **match set 표 3곳이 enum 원문을 노출.** `CurrentConfigTab`/`ListTab`/`MatchSetsTab`이 `{item.role}`을 `validation_optional` 그대로 출력(`MatchSetsTab.tsx:177`, `ListTab.tsx:210`).
4. **특수 상태가 없다.** C11(`roadaddr_building_shape_bundle`)의 **T-125 no-go·대표좌표 승격 보류**, 국가지점번호 **좌표=`core.sppn` 계산값(grid/center 파일은 좌표 원천 아님)**, `roadaddr_entrance`의 **기준월 일치 시 조건부 fallback** 같은 ADR-054 분류가 카탈로그/DTO/UI 어디에도 없다(`core/source_categories.py`의 `SourceDefaultRole`은 4값뿐).
5. 운영자가 "등록됨 + 무결성 OK"(RustFS/registry)를 "active serving 활용 중"으로 읽을 수 있다.

**정확한 부분**: `CurrentConfigTab`은 active match set을 정직하게 resolve하고 불명 시 `추정`/`알수없음`으로 degrade한다(`CurrentConfigTab.tsx:34-42`) — 이 탭만 active 기준을 올바르게 표시한다.

## source별 분류표 (ground truth ADR-054 vs UI 현재 vs 위험)

| source(category) | ADR-054 실제 분류 | UI 현재 표시 | 위험 |
|---|---|---|---|
| `roadname_hangul_full` 외 core 6종 | **active serving core**(좌표/텍스트 정본) | 녹색 `필수/권장 구성` | L (라벨 OK, 그룹화만 부재) |
| `roadaddr_entrance_full` | active serving, **기준월 일치 시 대표좌표 fallback(조건부)** | 녹색 `권장 구성`, 조건 미표기 | M |
| `zone_shape_full`(TL_SPPN_MAKAREA) | serving 유지하나 **zone context 전용·좌표 아님** | 녹색 `권장 구성` | M |
| `roadaddr_building_shape_bundle` (**C11**) | **검증 전용 + 대표좌표 승격 보류(T-125 no-go)** | 녹색 `검증 선택` — 일반 optional과 동일 | **H** |
| `national_point_grid_shape` / `_center` | **검증 전용**(좌표=`core.sppn` 계산값, 파일은 원천 아님) | 녹색 `검증 선택`, "좌표 아님" 표기 없음 | M |
| `detail_dong_shape_bundle` / `detail_address_db_full` | **상세주소 typed feature 후보**(호별 좌표 없음) | 녹색 `검증 선택` | M |
| `civil_service_institution_map` | **검증 전용 + 별도 POI 후보**(대표좌표 대체 금지) | 녹색 `보강 후보` — "보강"이 augmentation처럼 읽힘 | **H** |
| `address_db_full` / `building_db_full` | **검증 전용**(C16 key/row drift, 좌표·정본 대체 금지) | 녹색 `검증 선택` | L |
| `epost_*`(pobox/bulk) | postal-aux 보강, active serving 좌표 원천 아님 | 녹색 `보강 후보` | L |

H 2건(C11 no-go 미표시, 민원행정기관 "보강" 오해), M 4건, L 3건.

## 백엔드 데이터 gap (T-221 선행)

1. `SourceFileCategoryInfo`(`dto/source.py:74-89`)에 **serving-usage/promotion-status 필드가 없다** — `role`/`default_role`(UI 기본값)만 존재.
2. `GET /admin/source-file-categories`가 **active match set과 join하지 않아** "serving vs validation-only vs no-go"를 표현할 데이터가 응답에 없다.
3. `SourceDefaultRole`(`core/source_categories.py:17-22`)은 4값뿐이라 ADR-054의 분류(active serving core / computed / 검증 전용 / 승격 보류 no-go / 상세주소 typed feature 후보 / overlay·별도 feature)를 표현 불가.
4. C11의 T-125 no-go·승격 보류가 카탈로그/DTO 어디에도 없다(`validation_optional`로 `address_db` 등과 동일).
5. `enrichment_candidate`가 `civil_service`(검증 전용·POI)와 `epost`(postal-aux)를 한데 묶어 "보강(augment)" 의미가 ground truth(좌표 대체 금지)와 충돌.

## T-221 핸드오프 (UI 반영 구체 항목)

1. **read-only admin DTO/API 보강**: 카탈로그 응답에 `serving_usage` 분류 필드 추가 — `serving_core | active_serving_conditional | zone_context | computed_coordinate | validation_only | typed_feature_candidate | overlay_poi_candidate | promotion_blocked_no_go`. ADR-054 분류표를 ground truth 매핑으로. OpenAPI/typegen 갱신.
2. **C11 전용 배지**: `대표좌표 승격 보류(T-125 no-go: p95 22.801m, 100m초과 14,433, C4/C6/C7 악화)`를 UploadTab 카드 + match set 표에 노출.
3. **"active serving 포함 여부" 차원을 role 배지와 분리**해 UploadTab CategoryCard에 추가하고, `validation_only`/`no_go`는 녹색 `ok`가 아닌 **중립/경고 스타일**로 렌더(severityClass가 전부 녹색으로 만드는 문제 해결).
4. **ListTab '원천 파일 그룹' 표에 `active serving 포함/미포함(등록만)` 배지 컬럼** 추가 — 각 그룹 category를 active match set의 non-omitted item categories와 cross-reference(client-side join 가능, active match set detail 제공됨). "등록됨"≠"활용 중".
5. **match set 표 3곳**(`CurrentConfigTab:186`/`ListTab:210`/`MatchSetsTab:177`)의 `{item.role}`을 라벨로 변환하고 optional을 core와 시각적으로 분리.
6. **카드 note에 ADR-054 금지선** 표기: 국가지점번호 grid/center=`좌표=core.sppn 계산값, 이 파일은 검증 전용`; zone_shape=`zone context 전용, 좌표 아님`; civil_service=`주소 대표 좌표 대체 금지, 별도 POI 후보`; address/building_db=`좌표·정본 대체 금지, C16 drift 검증 전용`; detail_*=`상세주소 typed feature 후보, 호별 좌표 없음`; roadaddr_entrance=`기준월 일치 시 대표좌표 fallback`.
7. `enrichment_candidate`→`보강 후보` 문구를 serving augmentation으로 오해되지 않게 재문구화(예: `별도 기능 후보(서빙 미반영)`) 또는 `serving_usage` 분리.
8. T-224(파일 적재 UX의 active serving 포함 여부·validation-only/승격 보류 badge)와 일관되게 연결.

## API 응답 snapshot (구조 — 정적 role 노출 증거)

`GET /v1/admin/source-file-categories`의 각 항목 형태(`dto/source.py:74-89` 기준, 코드에서 도출):

```jsonc
{
  "kind": "roadaddr_building_shape_bundle",
  "label": "도로명주소 건물 도형",
  "default_role": "validation_optional",  // 정적 카탈로그 기본값
  "role": "validation_optional",          // == default_role, active match set 미반영
  "group_kind": "...", "optional": true, "expected_members": [...]
  // serving_usage / promotion_status 필드 없음  ← 본 gap
}
```

`role`은 active match set과 무관한 정적값이므로 C11=`validation_optional`이 `address_db_full`=`validation_optional`과 동일하게 나온다 — UI가 둘을 구분할 데이터가 응답에 없음을 보여준다. (라이브 호출 snapshot은 r3 DB·서버 기동이 필요해 본 감사에서는 응답 구조로 갈음하고, 라이브 캡처는 T-221 DTO 보강 후 회귀 fixture로 고정한다.)

## 결론

UI는 현재 source의 serving 활용도를 오해시킬 수 있고(특히 C11 no-go·민원행정기관 "보강"·국가지점번호 grid가 좌표 원천처럼 보임), 이는 **백엔드 카탈로그에 serving_usage/promotion_status 신호가 없어서** 발생한다. **T-221**에서 read-only admin DTO/API 보강(ADR-054 분류) + 위 8개 UI 항목을 구현해 `등록됨`/`검증 전용`/`active serving 미포함`/`승격 보류 no-go`를 명확히 구분하고, **T-224**(파일 적재 UX)와 일관시킨다.
