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

지도는 MapLibre GL JS + VWorld WMTS를 사용한다. `maplibre-vworld` package는 현재 확인 SHA인 `git+https://github.com/digitie/maplibre-vworld-js.git#7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`로 고정한다. T-044에서는 `v0.1.0` tag commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb` 기준 public API를 문서-only로 재확인했지만, npm registry에 0.1.0 package가 없어 dependency는 아직 바꾸지 않았다. 최신 upstream redaction helper는 `redactVWorldUrl()`이고, UI 내부에서는 기존 컴포넌트 계약을 유지하기 위해 `redactVWorldTileUrl` alias로 사용한다.

## 검증

WSL ext4 작업 디렉토리에서는 Windows `npm` 대신 Linux Node/npm을 사용한다. Windows `npm`은 UNC cleanup 오류를 낼 수 있어 검증 결과가 흔들릴 수 있다.

```bash
npm run lint
npm run type-check
npm run test
npm run build
```

저장소 루트의 `scripts/frontend_check.sh`는 Windows `npm`이 PATH에 잡힌 경우 즉시 실패하고, Linux Node/npm에서 `gen:types`, lint, type-check, unit test, build를 순서대로 실행한다. 의존성을 새로 받는 검증이면 `scripts/frontend_check.sh --install`을 사용한다.

Playwright와 실제 브라우저 렌더링 검증은 사용자 지시에 따라 Windows Node/브라우저 환경에서 수행한다. PR에는 Windows에서 실행한 명령, 브라우저, 스크린샷 경로를 함께 남긴다.

## 범위

- `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`
- OpenAPI 타입 생성: `../openapi.json` → `types/api.gen.ts`, `lib/schemas.gen.ts`
