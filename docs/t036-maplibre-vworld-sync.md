# T-036 `maplibre-vworld-js` main 동기화

## 목적

`kraddr-geo-ui`가 소비하는 `maplibre-vworld` GitHub dependency를 `digitie/maplibre-vworld-js`의 최신 `main` 커밋으로 올리고, 디버그 UI가 기존 click/error overlay 계약을 유지한 채 최신 package API를 사용할 수 있는지 검증한다.

이번 작업은 지도 컴포넌트 전체를 upstream `VWorldMap`으로 대체하는 작업이 아니다. 현재 디버그 UI는 reverse/geocode 화면 전용으로 다음 동작을 직접 보장한다.

- 지도 클릭 시 `(lon, lat)` 순서의 `{ x, y }` 값을 상위 디버그 폼에 전달한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 WebGL 지도를 만들지 않고 좌표 preview fallback을 표시한다.
- VWorld tile fetch 오류는 즉시 fatal overlay로 고정하지 않고, redacted URL warning과 누적 임계치로 처리한다.
- marker 갱신은 애니메이션 되튐 없이 즉시 반영한다.
- Next.js SSR 단계에서는 `next/dynamic(..., { ssr: false })` wrapper와 skeleton만 노출한다.

따라서 T-036의 범위는 dependency SHA 갱신, helper API 변경 반영, 소비자 build/test 검증, 문서화로 제한한다.

## 업스트림 확인

- 이전 고정 커밋: `11321fe8b8f4da849ee5c24ba18a27206a55e26e`
- 최신 확인 커밋: `c91c9f304669ce3f5fc4915f21186b23731d5816`
- 확인 명령: `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main`
- package name/version: `maplibre-vworld@1.0.0`
- package export:
  - root import: `maplibre-vworld`
  - CSS side effect import: `maplibre-vworld/style.css`
  - type declaration: `dist/index.d.ts`

## API 변경

최신 upstream은 tile URL redaction helper 이름을 `redactVWorldTileUrl()`에서 `redactVWorldUrl()`로 바꿨다. 또한 redaction 표기가 `[redacted]`에서 `***`로 바뀌었다.

`kraddr-geo-ui` 내부 컴포넌트는 아직 `redactVWorldTileUrl` 이름을 사용한다. 이 이름은 UI 내부 경계의 안정성을 위한 local alias이며, 실제 구현은 upstream `redactVWorldUrl()`을 그대로 소비한다.

```ts
export {
  getVWorldMaxZoom,
  getVWorldStyle as getVWorldRasterStyle,
  getVWorldTileUrl,
  isVWorldTileError,
  redactVWorldUrl as redactVWorldTileUrl,
  type VWorldLayerType
} from "maplibre-vworld";
```

테스트 기대값도 upstream 계약에 맞춰 `https://api.vworld.kr/req/wmts/1.0.0/***/Base/1/2/3.png`로 고정했다.

## 반영 파일

- `kraddr-geo-ui/package.json`: `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신한다.
- `kraddr-geo-ui/package-lock.json`: root dependency와 `node_modules/maplibre-vworld.resolved`를 같은 HTTPS SHA로 맞춘다. CI에서 SSH key 없이 설치되어야 하므로 `git+https`를 유지한다.
- `kraddr-geo-ui/lib/vworld.ts`: `redactVWorldUrl as redactVWorldTileUrl` alias를 둔다.
- `kraddr-geo-ui/tests/unit/vworld.test.ts`: 최신 upstream redaction 표기 `***`를 검증한다.

## 검증 환경

Windows `npm`이 WSL ext4 경로를 다룰 때 UNC 경로 정리 오류가 날 수 있으므로 이번 검증은 WSL Linux Node/npm으로 수행했다.

- Node.js: `/home/digitie/.cache/parking-radar-node-v22.15.0/bin/node`
- npm: `/home/digitie/.cache/parking-radar-node-v22.15.0/bin/npm`
- 실행 prefix: `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH`

검증 명령과 결과:

- `npm ci --ignore-scripts` → 통과. 기존 moderate advisory 7건은 유지.
- `npm run lint` → 통과.
- `npm run type-check` → 통과.
- `npm run test` → 7 files / 22 tests 통과.
- `npm run build` → 통과. `/debug/geocode`, `/debug/reverse`, `/admin/*` static route와 `/api/proxy/[...path]` dynamic route 생성 확인.

## 남은 작업

T-036 이후에는 사용자 지시에 따라 PR #22, PR #21, PR #20 순서로 신규 리뷰 코멘트를 확인하고, 반영 가능한 항목을 먼저 처리한다. 그 뒤 다음 기능 작업은 T-028 일변동 ZIP 로더다.
