# kraddr-geo-ui

`kraddr-geo-ui`는 `python-kraddr-geo` 백엔드의 내부 운영 콘솔이다. 브라우저는 Next.js Route Handler 프록시(`/api/proxy/*`)만 호출하고, 실제 백엔드 URL은 서버 환경변수 `KRADDR_GEO_API_INTERNAL_URL`에만 둔다.

## 실행

```bash
npm install
npm run gen:types
npm run dev
```

기본 진입점은 `/debug/geocode`다. `KRADDR_GEO_API_INTERNAL_URL`은 서버 사이드 프록시가 사용할 백엔드 주소이고, 브라우저는 `NEXT_PUBLIC_API_BASE_URL` 기본값인 `/api/proxy`만 호출한다.

`NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 지도 컴포넌트는 같은 크기의 좌표 프리뷰로 대체된다. 내부망/CI 환경에서 VWorld 도메인 등록이 끝나지 않아도 나머지 디버그 기능은 그대로 확인할 수 있다.

지도는 MapLibre GL JS + VWorld WMTS를 사용한다. `maplibre-vworld` package는 `git+https://github.com/digitie/maplibre-vworld-js.git#11321fe`로 고정하며, 패키징·타입·Next.js 호환 문제가 발견되면 이 UI에서만 우회하지 않고 해당 저장소도 적극 수정한다.

## 검증

```bash
npm run lint
npm run type-check
npm run test
npm run build
```

## 범위

- `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`
- OpenAPI 타입 생성: `../openapi.json` → `types/api.gen.ts`, `lib/schemas.gen.ts`
