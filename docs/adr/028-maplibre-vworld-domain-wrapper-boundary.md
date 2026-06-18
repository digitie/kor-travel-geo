# ADR-028: 디버그 UI 지도 구현은 `maplibre-vworld-js`를 최신으로 소비하고 domain wrapper로 경계화한다

- 상태: accepted, amended by ADR-032, ADR-063
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

> 최신 의존성 선택은 ADR-063을 우선한다. ADR-028의 초기 표현인 "완전 포팅"은 `kor-travel-geo-ui` 특화 기능까지 upstream으로 옮긴다는 의미가 아니라, 범용 VWorld/MapLibre primitive는 외부 VWorld MapLibre React 패키지에서 소비하고 이 저장소의 geocode/reverse/admin 특화 UX는 domain wrapper로 경계화한다는 의미로 개정됐다. 2026-05-28 T-044 재확인 범위는 `maplibre-vworld-js` 0.1.0 code/API 기준 문서-only 보강으로 한정하고, upstream 코드는 직접 수정하지 않는다.

## 컨텍스트

ADR-020은 Kakao Maps SDK를 제거하고 VWorld WMTS + MapLibre GL JS를 디버그 UI 지도 표준으로 정했다. 이후 `kor-travel-geo-ui`는 `digitie/maplibre-vworld-js`를 GitHub SHA로 소비하며 tile URL, style 생성, maxZoom, tile error 분류, URL redaction helper와 CSS를 upstream package에서 가져온다.

그러나 현재 `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`는 MapLibre map instance, marker, click callback, transient tile error overlay, fallback preview를 직접 wiring한다. 이 직접 wiring에는 두 성격이 섞여 있다. VWorld WMTS style, layer, marker primitive, package export 같은 범용 기능은 `maplibre-vworld-js`가 책임지는 것이 맞지만, `kor-travel-geo-ui`의 geocode/reverse 디버그 입력, 오류 overlay UX, API 응답 좌표 표시 같은 이 저장소 특화 기능은 `maplibre-vworld-js`로 밀어 넣지 않는다.

## 결정

후속 T-044에서 디버그 UI 지도 구현은 `maplibre-vworld-js`의 최신 public API를 소비하되, `kor-travel-geo-ui` 특화 기능은 이 저장소의 domain wrapper에 남긴다.

경계화의 의미는 다음과 같다.

1. `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`는 직접 `new maplibregl.Map(...)`, source/layer 생성, marker lifecycle, tile error 분류를 소유하지 않는다.
2. VWorld style/layer, tile URL, maxZoom, marker primitive, 공통 tile error/redaction, package `exports`/`types`/`style.css` 계약은 `maplibre-vworld-js`의 public API에서 제공한다.
3. `kor-travel-geo-ui`는 도메인별 wrapper를 유지한다. wrapper의 책임은 API 응답 좌표를 `(lon, lat)`로 넘기고, geocode/reverse 디버그 폼과 skeleton, 오류 overlay 문구, 내부 분석 상태를 연결하는 것이다.
4. `NEXT_PUBLIC_VWORLD_API_KEY` 미설정 fallback, SSR-safe 사용, transient tile error overlay, redacted logging, marker 즉시 이동, click callback `(lon, lat)` 순서가 기존 디버그 UI 동작과 동일해야 한다.
5. `maplibre-vworld-js`에 범용 기능·타입·패키징·테스트가 부족하면 T-044 문서-only 범위에서는 보완점을 기록하고, 실제 수정은 별도 upstream task/PR로 분리한다. 반대로 `kor-travel-geo`의 주소 디버깅, 작업 상태, 정합성/성능 분석, API 응답 표시처럼 이 라이브러리 특화 기능은 이 저장소에서 구현한다.
6. `maplibre-vworld-js`는 사용할 때마다 최신 `main` 또는 최신 stable release를 확인하고, 검증된 최신 버전으로 갱신한다. 임시로 오래된 SHA에 고정하는 것은 허용하지 않는다.

## 구현 절차

T-044의 2026-05-28 재확인 범위는 문서-only 작업으로 본다. `maplibre-vworld-js` 0.1.0 public API를 읽고 이 저장소의 소비 경계와 후속 구현 메모를 정리하되, upstream 코드는 직접 수정하지 않는다. 실제 UI wrapper 전환 또는 upstream 보강이 필요하면 별도 후속 task/PR로 분리한다.

1. `kor-travel-geo`에서 현재 `CoordinateMap` 계약을 목록화한다.
2. `maplibre-vworld-js` `v0.1.0` tag와 최신 `main`을 확인하고, 현재 dependency가 어느 기준에 있는지 비교한다.
3. 부족한 범용 upstream 기능은 T-044 안에서 직접 수정하지 않고 별도 upstream task/PR 후보로 기록한다.
   - VWorld layer/style helper
   - controlled/uncontrolled marker primitive
   - `flyToOptions`와 즉시 이동 옵션
   - VWorld tile error 분류와 URL redaction
   - SSR-safe import guidance 또는 wrapper
   - TypeScript props와 React 18/19 호환성
   - package `exports`, `types`, `style.css`, `dist` 산출물
4. `kor-travel-geo-ui` 특화 기능은 이 저장소에서 구현한다.
   - geocode/reverse/debug form과 지도 click 결과 연결
   - API 응답 좌표/주소/정합성 sample overlay
   - VWorld key 미설정 시 이 프로젝트의 좌표 preview fallback 문구와 layout
   - transient tile error를 이 프로젝트의 debug UX에 맞게 표시하는 overlay 임계치
   - 관리 UI 상태, benchmark, load/consistency 결과와 지도 연결
5. 실제 upstream 수정이 필요하면 별도 task에서 test/build를 통과시킨 뒤 PR을 올린다.
6. 실제 소비자 구현 PR에서는 `kor-travel-geo`에서 dependency를 검증된 upstream commit 또는 release/tag로 갱신한다.
7. 실제 소비자 구현 PR에서 `kor-travel-geo-ui`의 `CoordinateMap`은 upstream component/hook과 이 저장소 domain wrapper의 경계를 명확히 한다.
8. 실제 소비자 구현 PR에서 `kor-travel-geo-ui`의 `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 수행한다.
9. Playwright 또는 브라우저 검증이 가능한 환경에서는 실제 소비자 구현 PR에서 `/debug/geocode`, `/debug/reverse`의 지도 표시, marker 이동, click reverse 입력, tile error/fallback 상태를 확인한다.

## 결과 기준

T-044 완료 조건:

- `maplibre-vworld-js` 0.1.0 tag/commit, package manifest, public export, `VWorldMap`, marker/layer primitive, helper API를 문서화한다.
- 현재 `CoordinateMap.tsx`가 직접 소유하는 domain 동작과 0.1.0 public API로 대체 가능한 범용 primitive를 문서화한다.
- upstream 코드를 직접 수정하지 않았다는 점과 실제 UI/dependency 전환은 후속 PR에서 검증해야 한다는 점을 명시한다.
- 상세 기록은 `docs/t044-maplibre-vworld-010-review.md`에 둔다.

## 위험과 제약

- 지도 컴포넌트는 브라우저/WebGL 의존성이 강하므로 SSR 단계 import가 다시 생기면 Next.js build 또는 hydration에서 깨질 수 있다.
- VWorld API key는 브라우저 노출 키이지만 저장소와 PR 본문에 평문으로 남기지 않는다.
- upstream SHA 또는 release 갱신은 lockfile `resolved`가 `git+https`인지 확인한다. CI는 SSH key 없이 설치되어야 한다.
- 2026-05-28 현재 `maplibre-vworld@0.1.0`은 npm registry에서 확인되지 않았다. 실제 소비는 GitHub tag 또는 commit SHA 기준으로 검증해야 한다.
