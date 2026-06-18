# kor-travel-geo-ui

`kor-travel-geo-ui`는 `kor-travel-geo` 백엔드의 내부 운영 콘솔이다. 브라우저는 Next.js Route Handler 프록시(`/api/proxy/*`)만 호출하고, 실제 백엔드 URL은 서버 환경변수 `KTG_API_INTERNAL_URL`에만 둔다.

## 실행

```bash
npm install
npm run gen:types
npm run dev -- --port 12505
```

기본 진입점은 `/debug/geocode`이며 공식 로컬 UI 포트는 `12505`이다. `KTG_API_INTERNAL_URL`은 서버 사이드 프록시가 사용할 백엔드 주소이고, 브라우저는 `NEXT_PUBLIC_API_BASE_URL` 기본값인 `/api/proxy`만 호출한다. 지오코딩/역지오코딩 디버그 화면은 `/v2/geocode`, `/v2/reverse` REST API를 사용하며, 관리·정규화·EXPLAIN 화면은 아직 `/v1/admin/*` 운영 API를 사용한다.

VWorld 키가 없으면 지도 대신 같은 크기의 좌표 프리뷰 UI를 보여 준다. MapLibre를 대체하는 별도 fallback 지도는 두지 않는다. 내부망/CI 환경에서 VWorld 도메인 등록이 끝나지 않아도 나머지 디버그 기능은 그대로 확인할 수 있다. 실행 중에는 `/api/runtime-config`가 Python API `.env`의 `KTG_VWORLD_API_KEY`를 우선 읽어 브라우저에 전달한다. 이 값이 없으면 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용한다. `/admin/settings`에서 VWorld 인증키를 입력하면 브라우저 localStorage override로 저장되고, 기본값 버튼을 누르면 `.env` 기본값으로 되돌아간다.

지도는 MapLibre GL JS + VWorld WMTS를 사용한다. `maplibre-vworld-react` package는 현재 확인 SHA인 `a7cb0f8f41ec00b44b1d106664506730b87033bd`의 GitHub tarball로 고정한다. 2026-06-18 기준 npm registry에는 공개 package가 없어 HTTPS tarball URL을 유지한다. `CoordinateMap`은 upstream `VWorldMapView`, `Marker`, `useMap`, `useMapLoaded`, `redactVWorldUrl()`를 직접 소비하고, key 미설정 안내와 tile error overlay 임계치 같은 프로젝트 특화 UX만 감싼다. root tarball이 monorepo source를 포함하므로 TypeScript, Vitest, Next.js webpack, Next.js 16 Turbopack alias를 함께 유지한다.

## 검증

프론트엔드 실행과 정적 검증은 WSL ext4 작업 디렉토리에서 Linux Node/npm으로 수행한다. Windows `npm`은 UNC cleanup 오류를 낼 수 있어 검증 결과가 흔들릴 수 있다.

UI를 수정할 때는 [`docs/DESIGN-RULES.md`](docs/DESIGN-RULES.md)의 StyleSeed 기반 운영 콘솔 규칙을 먼저 확인한다. 새 색상과 컴포넌트를 늘리기 전에 `app/globals.css`와 `tailwind.config.ts`의 semantic token으로 표현할 수 있는지 본다.

```bash
npm run lint
npm run type-check
npm run test
npm run build
npx react-doctor@latest . --offline --verbose --json
```

모든 프론트엔드 작업 뒤에는 React Doctor를 실행하고, 새 경고가 나오면 수정한 뒤 같은 명령을 다시 실행해 경고가 남지 않았음을 확인한다.

브라우저 e2e는 Playwright로 수행하되 Windows Node/브라우저 환경에서만 실행한다. WSL에서는 `npm run test:e2e`나 `npx playwright test`를 실행하지 않는다. UI 서버는 WSL에서 실행한다. WSL 서버에 Windows Playwright를 붙일 때는 `next dev --hostname 0.0.0.0 --port 12505` 또는 `next start --hostname 0.0.0.0 --port 12505`로 띄우고, Windows 터미널에서 WSL IP를 `PLAYWRIGHT_BASE_URL`로 지정한다. PR 완료 전 e2e는 Chrome 기준 `chromium` project와 Firefox 기준 `firefox` project를 모두 실행한다.

```bat
set PLAYWRIGHT_BASE_URL=http://<WSL_IP>:12505
npx playwright test --config playwright.config.ts --project chromium --workers 1
npx playwright test --config playwright.config.ts --project firefox --workers 1
```

현재 e2e는 `/debug/geocode`와 `/debug/reverse`가 `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse`, `/api/proxy/v2/regions/within-radius`로 POST하는지, 도로명/지번/좌표/반경 입력이 v2 body로 변환되는지, geocode 도형 옵션이 `include_geometry`로 전달되는지, 잘못된 입력에서 요청을 보내지 않는지를 검증한다. `navigation.spec.ts`는 좌측 메뉴 반복 이동 중 Next 기본 오류 화면(`This page couldn’t load`)으로 떨어지지 않는지 확인한다. `vworld-map.spec.ts`는 mock 없이 Python API `.env`에서 읽은 VWorld 키로 MapLibre canvas와 VWorld WMTS 타일 응답을 확인한다.

## Docker 실행

저장소 루트의 `scripts/docker_app.sh`를 사용한다. 이 스크립트는 API/UI 이미지를 빌드하고, 컨테이너 실행 시 `.env` 또는 `kor-travel-geo-ui/.env.local`에서 VWorld 키와 DB/RustFS 접속 설정을 읽어 환경변수로 주입한다. 키 값은 출력하지 않는다. PostgreSQL/PostGIS와 RustFS는 이 프로젝트에서 직접 구동하지 않고 이미 동작 중인 접속 대상을 사용한다.

```bash
scripts/docker_app.sh build-ui
scripts/docker_app.sh up-ui
```

API와 UI를 함께 띄우려면 `scripts/docker_app.sh build` 뒤 `scripts/docker_app.sh up`을 사용한다. 기본 실행은 Docker bridge network와 host port mapping을 사용하므로 브라우저 진입점은 `http://127.0.0.1:12505/debug/geocode`다. API 컨테이너는 `.env`의 `KTG_PG_DSN`과 `KTG_RUSTFS_*` 접속 설정으로 이미 동작 중인 DB와 bucket에 붙는다.

저장소 루트의 `scripts/frontend_check.sh`는 Windows `npm`이 PATH에 잡힌 경우 즉시 실패하고, Linux Node/npm에서 `gen:types`, lint, type-check, unit test, build를 순서대로 실행한다. 의존성을 새로 받는 검증이면 `scripts/frontend_check.sh --install`을 사용한다.

Playwright와 실제 브라우저 렌더링 검증은 Windows Node/브라우저 환경에서만 수행한다. WSL headless Chromium은 공유 라이브러리 누락으로 반복 실패하므로 사용하지 않는다. PR에는 Windows에서 실행한 명령과 Chrome/Firefox 브라우저별 결과를 함께 남긴다.

Firefox 기준으로 지도 로딩을 재현할 때는 Windows 터미널에서 `PLAYWRIGHT_BROWSER=firefox`를 지정한다.

```bat
set PLAYWRIGHT_BASE_URL=http://localhost:12505
set PLAYWRIGHT_BROWSER=firefox
npx playwright test --config playwright.config.ts --grep "VWorld 지도" --workers 1
```

## 범위

- `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`
- OpenAPI 타입 생성: `../openapi.json` → `types/api.gen.ts`, `lib/schemas.gen.ts`
