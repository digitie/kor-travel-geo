# v2 Dataset Version

## 요약

`POST /v2/dataset/version`과 `POST /v2/dataset/history`는 외부 소비자가 "서빙 중인 주소 DB가 바뀌었는가"를 값싸게 감지하고, 바뀌었다면 언제·어떤 종류의 변경이 있었는지 이력을 확인하는 두 endpoint다. 결정 기록은 [ADR-067](../../adr/067-external-dataset-version-api.md), 설계 정본은 [t291-dataset-version-external-api.md](../../t291-dataset-version-external-api.md)다.

candidate 목록 endpoint(geocode/reverse/search)와 달리 **Python 라이브러리로는 공개하지 않는다**(ADR-039 — 라이브러리는 후보 목록 API만 공개) — REST 전용이다.

모든 응답에 `Cache-Control: no-store`가 붙는다([v2 공통 규약](README.md) 참조). 권장 폴링 주기는 **60초 이상**이다.

## 계약 4항

1. `version_token`은 불투명 값이다 — **동등 비교만 허용**하고 파싱·정렬은 계약 위반이다.
2. 토큰이 같으면 서빙 데이터셋이 바뀌지 않았다. **역은 보증하지 않는다** — 동일 데이터를
   재적재해도 새 토큰이 발급될 수 있다(허용된 과잉 감지, 거짓 음성보다 안전한 방향).
3. `reference_months`는 도출에 실패하면 응답에서 생략될 수 있으며(생략 시 토큰만이 신뢰
   신호), 비단조다(복원 후 과거 월로 역행 가능).
4. 이력 보존은 **보증하지 않는다** — hot-swap 복원 시 백업 시점 이후 이력이 소멸할 수 있다.

## `POST /v2/dataset/version`

폴링 대상 endpoint다. `known_version`을 함께 보내면 변경 여부를 판정해 응답한다.

### 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `known_version` | string | 없음 | 이전에 저장한 `version_token`. 형식 `^dv1-[0-9a-f]{32}$` — 불일치 시 구조화 400. |

### 출력

```json
{
  "status": "OK",
  "query_id": "...",
  "input": { "known_version": "dv1-4c2e0b7a9d315f68c0aa41e2b8d97f13" },
  "available": true,
  "changed": true,
  "known_version_found": false,
  "current": {
    "version_token": "dv1-9f31c8ab02de47f6a1b5c033e8d21c70",
    "activated_at": "2026-08-20T03:12:45+09:00",
    "change_type": "full",
    "reference_months": {
      "juso": "202607", "parcel_link": "202607", "locsum": "202606",
      "navi": "202606", "shp": "202606"
    },
    "reference_months_mixed": true
  }
}
```

- `available`: 활성 release가 하나도 없으면 `false`이고 `current`는 생략된다(HTTP 200 — 오류
  아님). 신규/빈 DB에서 정상적으로 발생하는 상태다.
- `known_version`을 보내지 않으면 `changed`/`known_version_found`가 생략된다 — 현재 버전
  조회만 하는 호출이다.
- `changed`: `known_version`이 현재 토큰과 다르면 `true`.
- `known_version_found`: 그 토큰이 현재 원장(활성+비활성 이력 포함)에 남아 있으면 `true`.
  `false`면 이력이 리셋됐다는 뜻(복원 등)이며 **전체 재동기화** 규약이다.
- `change_type`: `"full"`(전체 재동기화 필요) 또는 `"delta"`(증분 갱신 가능) 2종뿐이다.
- `reference_months`: 원천별 `YYYYMM` map. 키 어휘는 `juso`/`parcel_link`/`locsum`/`navi`/
  `shp`/`roadaddr_entrance`/`sppn_makarea`/`pobox`로 고정이다(`pobox`는 현재 어떤 writer도
  방출하지 않는 예약 키). 값이 없는 필드는 REST 응답에서 생략된다(`null` 아님).
- `reference_months_mixed`: 정규화된 `reference_months` 값들이 서로 다르면 `true`.

## `POST /v2/dataset/history`

변경 이력을 최신순으로 반환한다.

### 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `since_version` | string | 없음 | 이 토큰의 활성화 시각 이후 항목만(자신 제외). 원장에 없으면 최신 페이지를 반환(이력 리셋 규약). |
| `limit` | integer | `20` | 1~100. |
| `cursor` | string | 없음 | 이전 응답의 `next_cursor`. opaque — 파싱 금지, 해석 실패 시 구조화 400. |

### 출력

```json
{
  "status": "OK", "query_id": "...",
  "input": { "limit": 20 },
  "since_found": true,
  "entries": [
    { "version_token": "dv1-9f31…", "activated_at": "2026-08-20T03:12:45+09:00",
      "change_type": "full",
      "reference_months": { "juso": "202607" }, "reference_months_mixed": false },
    { "version_token": "dv1-77aa…", "activated_at": "2026-07-19T02:41:03+09:00",
      "change_type": "delta" }
  ],
  "next_cursor": "eyJ…"
}
```

- 정렬: 활성화 시각(없으면 생성 시각) 내림차순, 동률 시 `version_token` 내림차순 — 커서가
  내부 id를 담지 않으므로 tiebreak를 토큰으로 둔다.
- `since_found`: `since_version`을 보내지 않으면 생략. 원장에서 못 찾으면 `false`이며,
  이 경우에도 최신 페이지는 정상 반환된다(에러 아님).
- `next_cursor`: 다음 페이지가 있을 때만 포함. 마지막 페이지면 생략.
- entry 모델은 `/v2/dataset/version`의 `current`와 동일하다.

## 소비자 프로토콜

1. `known_version`을 포함해 폴링(≥60초). `changed:false` → 무동작.
2. `changed:true, known_version_found:true` → `history`를 `since_version`으로 소급, 각
   entry의 `change_type`별로 갱신(`delta`=증분, `full`=전체) 후 새 토큰을 저장.
3. `changed:true, known_version_found:false` → 전체 재동기화 후 새 토큰 저장.
4. 저장한 토큰은 불투명 값으로만 취급한다 — 위 "계약 4항" 참조.

## 예시

```bash
curl -X POST "http://localhost:12501/v2/dataset/version" \
  -H "Content-Type: application/json" \
  -H "X-KTG-API-Key: ${KTG_PUBLIC_API_KEY}" \
  -d '{"known_version":"dv1-4c2e0b7a9d315f68c0aa41e2b8d97f13"}'
```

```bash
curl -X POST "http://localhost:12501/v2/dataset/history" \
  -H "Content-Type: application/json" \
  -H "X-KTG-API-Key: ${KTG_PUBLIC_API_KEY}" \
  -d '{"since_version":"dv1-4c2e0b7a9d315f68c0aa41e2b8d97f13","limit":20}'
```

## 관련

- 엣지 케이스별 전체 거동표(hot-swap/rollback/restore/이력 리셋 등)는
  [ADR-067 "결과"](../../adr/067-external-dataset-version-api.md#결과) 절이 정본이다.
- admission scope(`dataset`, 전역 `address` 예산 제외)는
  [t145-backpressure-failfast.md](../../t145-backpressure-failfast.md)를 본다.
