# T-036 `maplibre-vworld-js` main 동기화

## 목적

`kraddr-geo-ui`가 소비하는 `maplibre-vworld` GitHub dependency를 `digitie/maplibre-vworld-js`의 최신 `main` 커밋으로 올리고, 디버그 UI가 기존 click/error overlay 계약을 유지한 채 최신 package API를 사용할 수 있는지 검증한다.

이번 작업은 지도 컴포넌트 전체를 upstream `VWorldMap`으로 대체하는 작업이 아니었다. 현재 디버그 UI는 reverse/geocode 화면 전용으로 다음 동작을 직접 보장한다.

- 지도 클릭 시 `(lon, lat)` 순서의 `{ x, y }` 값을 상위 디버그 폼에 전달한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 WebGL 지도를 만들지 않고 좌표 preview fallback을 표시한다.
- VWorld tile fetch 오류는 즉시 fatal overlay로 고정하지 않고, redacted URL warning과 누적 임계치로 처리한다.
- marker 갱신은 애니메이션 되튐 없이 즉시 반영한다.
- Next.js SSR 단계에서는 `next/dynamic(..., { ssr: false })` wrapper와 skeleton만 노출한다.

따라서 T-036의 범위는 dependency SHA 갱신, helper API 변경 반영, 소비자 build/test 검증, 문서화로 제한한다.

T-044에서는 이 보류분을 해소한다. 목표는 `CoordinateMap.tsx`의 직접 MapLibre lifecycle 소유를 줄이고, upstream `maplibre-vworld-js`의 최신 `VWorldMap` 또는 동등한 Hook/component를 감싸는 domain wrapper로 만드는 것이다. 부족한 범용 upstream 기능이 있으면 `python-kraddr-geo`에 workaround를 쌓지 않고 `digitie/maplibre-vworld-js`를 직접 수정한다. 단, geocode/reverse 입력 연결, 정합성/성능/적재 overlay, key 미설정 fallback 문구와 layout처럼 이 프로젝트에만 의미가 있는 기능은 `kraddr-geo-ui` wrapper에서 구현한다.

2026-05-27 후속 T-048에서 최신 upstream `main`은 `1a28b1099ab6c9c03e892e469974aee8c07deda1`로 다시 확인되었다. 현재 dependency는 이 SHA로 갱신됐으며, 최신성 확인과 책임 경계는 ADR-032를 따른다.

## 업스트림 확인

- 이전 고정 커밋: `11321fe8b8f4da849ee5c24ba18a27206a55e26e`
- T-036 당시 확인 커밋: `c91c9f304669ce3f5fc4915f21186b23731d5816`
- T-036 당시 커밋 추적: stable tag가 아니라 `git ls-remote`로 확인한 upstream `main` 직접 커밋이다. package export/helper 이름 변경을 소비자 쪽에서 검증해 고정했다.
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

- `kraddr-geo-ui/package.json`: T-036 당시 `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신했다.
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

T-036 직후의 PR #22~#20 리뷰 후속은 PR #24로 처리했다. 남은 지도 작업은 T-044다.

T-044 완료 조건:

- `maplibre-vworld-js`가 click callback, marker 제어, `flyToOptions`, tile error hook/redaction, SSR-safe 사용법 같은 범용 public API와 test를 제공한다.
- `kraddr-geo-ui`가 geocode/reverse/debug/admin 화면 특화 상태, key 미설정 fallback 문구, API 응답 overlay, transient overlay 임계치를 domain wrapper에서 제공한다.
- 필요한 기능이 upstream에 없으면 `digitie/maplibre-vworld-js` PR을 먼저 만들고, merge 또는 검증된 commit SHA를 `kraddr-geo-ui`가 소비한다.
- `CoordinateMap.tsx`는 직접 MapLibre primitive lifecycle을 소유하지 않고 upstream component/hook을 감싸는 얇은 wrapper가 된다.
- `kraddr-geo-ui`의 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 다시 수행한다.
