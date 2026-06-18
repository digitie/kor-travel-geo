# ADR-032: `maplibre-vworld-js`는 최신으로 소비하고 `kor-travel-geo` 특화 기능은 이 저장소에 둔다

- 상태: accepted, dependency choice superseded by ADR-063
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

## 컨텍스트

> 최신 의존성 선택은 ADR-063을 우선한다. 이 ADR의 책임 경계 원칙은 유지하지만, `kor-travel-geo-ui`가 소비하는 패키지는 `maplibre-vworld-js`가 아니라 GitHub `digitie/maplibre-vworld-react` tarball로 바뀌었다.

ADR-020과 ADR-028은 VWorld WMTS + MapLibre GL JS 전환 과정에서 `digitie/maplibre-vworld-js`를 적극 보강 대상으로 두었다. 이 방향은 유지한다. 다만 "완전 포팅"이라는 표현은 `kor-travel-geo-ui`의 지오코딩/역지오코딩 디버그 UX, 정합성 sample overlay, 적재/성능 분석 화면처럼 이 프로젝트에만 의미가 있는 기능까지 upstream package로 옮기는 것으로 오해될 수 있다.

또한 `maplibre-vworld-js`는 별도 저장소에서 빠르게 바뀌고 있다. GitHub dependency를 오래된 SHA에 고정하면 최신 upstream의 bug fix, package export, 타입 보강, marker/overlay 기능을 놓칠 수 있다. 따라서 이 저장소에서 `maplibre-vworld` 의존성을 만질 때는 항상 최신 `main` 또는 최신 stable release를 먼저 확인해야 한다.

## 결정

`kor-travel-geo-ui`는 `maplibre-vworld-js`를 항상 최신 확인 버전으로 소비한다. 현재 `kor-travel-geo-ui/package.json`과 lockfile은 upstream `main` commit `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`을 사용한다. 2026-05-31 기준 package version은 `0.1.2`이고, `v0.1.2` 이후 `main` 차이는 문서 보강 commit 2개다. npm registry에는 아직 `maplibre-vworld` package가 없어 GitHub SHA를 유지한다.

책임 경계는 다음과 같다.

1. `maplibre-vworld-js` 책임:
   - VWorld tile URL, layer/style helper, layer별 `maxZoom`, attribution
   - MapLibre map/marker/popup/cluster 같은 범용 primitive
   - click/error/flyTo hook처럼 다른 VWorld MapLibre 소비자도 재사용할 수 있는 component 또는 hook
   - VWorld tile error 판별, URL redaction, key 노출 방지 helper
   - package `exports`, `types`, `style.css`, `dist` 산출물, React/Next.js/Vite 호환성
   - 범용 동작의 단위 테스트와 예제
2. `kor-travel-geo` / `kor-travel-geo-ui` 책임:
   - geocode/reverse/debug/admin 화면의 입력 상태와 지도 click 결과 연결
   - API 응답 좌표, 주소 후보, 정합성 sample, 성능 benchmark 결과를 지도에 overlay하는 domain wrapper
   - `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 시 이 프로젝트 UI 문맥에 맞는 좌표 preview fallback
   - transient tile error를 이 프로젝트의 디버그 UX에 맞게 몇 회까지 warning으로 볼지 결정하는 임계치와 표시 문구
   - load job, consistency report, backup/restore, query benchmark 같은 운영 콘솔 상태와 지도 상호작용

즉, upstream은 "VWorld + MapLibre를 잘 쓰기 위한 범용 도구"를 제공하고, 이 저장소는 "한국 주소 지오코딩 라이브러리의 디버깅·관리 경험"을 구현한다.

## 실행 규칙

- `maplibre-vworld` dependency를 건드리는 PR은 `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main` 또는 최신 release 확인 결과를 문서와 PR 본문에 남긴다.
- npm registry stable release가 없거나 아직 검증 전이면 GitHub dependency는 `git+https://...#<verified-sha>` 형식으로 둔다. SSH `git@github.com:` 또는 `github:` shorthand로 lockfile이 바뀌면 CI 환경에서 key 없이 설치되지 않을 수 있으므로 되돌린다.
- 최신 upstream을 올린 뒤 `kor-travel-geo-ui`에서 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 실행한다.
- 최신 upstream에 범용 결함이 있으면 별도 upstream task/PR로 분리한다. 이 저장소에는 장기 workaround를 쌓지 않는다. 단, T-044 0.1.0 재확인 범위는 문서-only이므로 upstream 코드를 직접 수정하지 않는다.
- 프로젝트 특화 기능은 upstream PR로 보내지 않는다. 필요한 경우 `maplibre-vworld-js`에는 범용 extension point만 추가하고, 실제 주소 디버그/관리 동작은 이 저장소 wrapper에서 구현한다.
- `VWorldMap` 또는 hook으로 포팅하더라도 `CoordinateMap.tsx`는 완전히 사라질 필요가 없다. 남아 있다면 upstream primitive를 감싸는 domain wrapper여야 하며, 직접 MapLibre lifecycle을 다시 소유하지 않아야 한다.

## 결과

- 현재 `kor-travel-geo-ui`는 `maplibre-vworld`를 `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`로 유지한다.
- `CoordinateMap`은 upstream `VWorldMap`/`Marker`/hook을 감싸는 domain wrapper로 전환했다. "모든 지도 관련 기능을 upstream으로 이동"이 아니라 "범용 지도 primitive는 upstream API로 소비하고, `kor-travel-geo-ui` 특화 UX는 이 저장소에서 명확히 경계화"로 재정의한다.
- 이후 maplibre-vworld 관련 작업은 최신성 확인, 책임 경계, 양쪽 저장소 검증 결과를 함께 남긴다.
