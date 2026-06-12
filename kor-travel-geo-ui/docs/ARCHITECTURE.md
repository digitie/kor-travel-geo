# ARCHITECTURE

`kor-travel-geo-ui`는 자체 DB 연결 없이 Next.js Route Handler가 `kor-travel-geo` REST API를 프록시한다.

```mermaid
flowchart LR
  B["Browser"] --> N["Next.js /api/proxy"]
  N --> A["FastAPI /v1/* + /v2/*"]
  A --> P["PostgreSQL + PostGIS"]
```

주요 화면은 디버그(`/debug/*`)와 운영(`/admin/*`)으로 나뉜다. 지오코딩/역지오코딩 디버그 화면은 `/v2/geocode`, `/v2/reverse`를 사용하고, 운영·정규화·EXPLAIN 화면은 `/v1/admin/*`를 사용한다. `types/api.gen.ts`는 루트 `openapi.json`에서 생성하고, 손수 작성하는 입력 검증은 `lib/schemas.ts`에 둔다.
