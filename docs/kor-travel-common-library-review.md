# 공통 라이브러리 비교·구현·검증 보고서

> 현재 운영 이미지와 같은 입력으로 검증한 성능 실측을 기록한다. 이전 개정의 실행 증거는 해당 소스와 이미지에 연결한다.

## 결정과 범위

공통으로 사용할 수 있는 컴포넌트와 코드는 kor-travel-common으로 옮긴다. 같은 패키지를 쓰는 앱은 정확 버전·배포 산출물·lock integrity·실제 설치 파일을 맞춘다. 도메인 의존성을 모든 앱에 설치하지 않는다. 표는 TanStack Table과 Virtual을 사용하는 공통 VirtualTable, 웹 부품은 shadcn/ui 방식의 Radix 조합을 사용한다. Form은 React Hook Form/Zod, 화면 상태는 Zustand, 글꼴은 Pretendard를 적용한다.

Geo·Weather·Transport·Pinvi 웹/모바일·Concierge·Manager 양 호스트를 직접 처리한다. Map은 기존 사용자 분담에 따라 Claude가 소스·빌드·배포를 소유한다. Map을 이번 배포 완료 목록에 포함하지 않는다. 모바일 native 실기기·EAS·스토어 검증은 웹 이미지 검증과 별도다.

### 장점과 비용

| 영역 | 이점 | 비용과 구현 경계 |
| --- | --- | --- |
| 공통 표·overlay | 정렬·가상화·포커스·접근성 결함을 한 구현에서 수정한다 | 공통 회귀가 여러 앱에 영향을 준다. 공통 계약 시험과 소비 앱 화면 검증을 함께 유지한다 |
| 버전·산출물 | 같은 semver의 다른 bytes와 앱별 임의 재포장을 막는다 | producer commit·catalog commit·SRI·설치 파일을 따로 결박한다 |
| 폼·상태·폰트 | 반복 코드와 화면별 동작 차이를 줄인다 | 도메인 schema·인증·API 오류·상태 수명은 앱이 소유한다 |
| 지도 어댑터 | VWorld/MapLibre·worker·웹/RN 연결을 같은 상류에서 소비한다 | RN/GL JS의 정확 style-spec 요구를 무시한 강제 override를 하지 않는다 |
| 빌드 캐시 | GDAL·공유 라이브러리 wheel·npm·앱별 Next cache 재사용 | ABI·glibc·GDAL 버전에 따라 cache를 나누고 실제 hit를 기록한다. 캐시 설정만으로 속도 개선을 주장하지 않는다 |
| Docker Manager | 기존 G·프로젝트 lease·공식 service-release·상태 보존 경로 재사용 | 이미지 생성·native 검사·실제 적용·화면 수용을 별도로 기록한다 |
| 모바일 Tailwind4 | 웹과 공통 token 및 스타일 도구 축을 맞춘다 | NativeWind5와 react-native-css는 RC다. 웹 CI 성공을 native 기기 수용으로 바꾸지 않는다 |

관리 UI의 `node_modules`를 Next.js 산출물 전에 deps 단계에서 복사하도록 변경했다. UI CSS만 바꾼 로컬 amd64 비교에서 의존성 복사 레이어를 재사용하고 새 CSS 반영 및 두 이미지의 native 모듈과 로그인 응답을 확인했다. 레이어 내보내기 시간은 23.1초에서 1.2초였다. 권한을 바로잡은 ARM 정규 빌드가 18분 40초에 완료됐다. npm 설치 레이어를 재사용하고 새 실행 의존성 레이어를 생성했다. [Geo PR #652](https://github.com/digitie/kor-travel-geo/pull/652)

## 배포와 미완료 항목

현재 성능은 운영 이미지와 요청 조건을 함께 기록한다. Transport의 `b7509988` 철도 내보내기는 첫 200이 3,067ms였고 같은 ETag의 304 세 건이 141·263·176ms였다. 커서 다음 페이지와 1,466행 전체 수를 검증했다. 표본 수는 첫 응답 1건과 조건부 3건이다.

Transport는 API 프로세스 기동 후 백그라운드에서 같은 워커의 철도 입력 지문을 한 번 읽는다. 준비 조회에는 최대 10초를 할당하고 API readiness는 독립적으로 응답한다. 준비가 끝난 후 실제 HTTP 200을 보낸 동일 데이터 1,466건 로컬 비교에서 준비된 본문 기준 중앙값이 154ms에서 103ms였다. PostgreSQL과 프로세스 정리 조건을 바꾼 별도 비교에서도 196ms에서 129ms였다. 철도 입력 데이터의 리비전이 바뀌면 새 지문을 계산한다. 준비되지 않은 본문에서 지연 개선은 표본 간 일관되지 않았다. Odroid `8103733`에 배포한 후 첫 진단은 200·7,766ms, 조건부 응답은 304·305ms였다. 첫 요청에서 입력 지문 SQL은 다시 실행하지 않았고 1,466행 세대의 응답 본문을 새로 생성했다. SQL은 38회·2,298ms였고 첫 응답 1초 목표는 미달했다. [Transport PR #234](https://github.com/digitie/kor-travel-transport/pull/234)

동일 1,466행을 새 릴리스 SHA로 미리 발행한 로컬 PostgreSQL 검증에서 첫 HTTP 200은 311ms에서 42ms로 줄었고 본문·ETag·커서가 일치했다. 같은 검증에서 이전 API가 살아 있을 때 미리 발행하면 이전 API가 공유 포인터를 되돌릴 수 있었다. 운영 첫 응답까지 보장하려면 이전 API와 수집이 멈춘 시점부터 새 API가 시작하기 전까지 발행해야 한다. 현재 Manager SDK #627에는 이 실행 지점이 필요하다.

Weather `b5039fa8` 단기예보는 현재 승인 위치 기준 1,078격자다. 조회 시점에는 349격자와 1,453곳 중 514곳이 6시간 이내 갱신됐다. 현재 3시간마다 최대 300격자이므로 6시간 내 최대 600격자다. 6시간 내 전체를 한 번씩 갱신하는 데 회당 최소 539격자와 하루 단기예보 논리 요청 4,312건이 필요하다. 소비자 간 키가 공유되므로 운영 승인 한도와 전체 사용량을 확인해야 한다.

2026-11-21 한국 시간까지 확인한 소스와 이미지 기준으로 기록한다. 이후에 적용한 이미지의 결과는 해당 커밋과 관찰 시각을 함께 적는다.

| 대상 | 실제 수용 | 후속 진행·한계 |
| --- | --- | --- |
| Weather | PR #279 `2b269b03` ARM API·코드 서버·웹 적용 및 SDK627 확인. 기존 27개 상태(24 RUN·3 STOP) 복원, 모바일 390px에서 로그인·지도·로그아웃 확인 | 이전 `b5039fa8` 저장 단기예보 진단은 200·16.469초, 새 배포 첫 진단은 200·5.790초. 서로 다른 시각·부하에서 한 건씩 측정했다. 첫 응답 원천은 `stale`이고 503 재발률은 운영 관찰이 남았다 |
| Transport | PR #234 `8103733` ARM 정규·native·SDK627 코어 적용. 기존 Transport 일정 20개 복원, PostgreSQL 스키마 `0045` 유지, 공개 주차 화면 390px·1280px HTTP 200 | 코어 전환 중 코드 서버 상태 복원과 이미지 시작 구간에서 몇 분간 끊겼고 세 역할이 정상 상태로 회복했다. 별도로 배포된 Admin과 Fuel 및 게이트웨이는 코어 변경 전의 이미지와 컨테이너를 유지했다 |
| Fuel 공개 지도 | PR231 병합b7509988·필수CI5개 통과·UI690/API42/gateway39/producer140 검증. 실제 Odroid12307 gateway·12308 web 기동/healthy·Manager627 공개 adopt/verify 완료 | 실제 기존backend4a801 의존의 예비 브라우저 검증에서5폭 전체화면·메뉴/제목 없음·실제 VWorld256px 타일6개 decode·사용자 동작 후 위치 이동 확인. 후속 예비 검증은 지도 유가·가격 이력200/JSON·상세 닫기·터치 필터·필터 후 확대·위치 거절 fallback을 통과했다. 다만 실제 마커 전환에서 지역 라벨 null을 offsetWidth로 읽는 앱 오류가 확인됐다. 수정 PR232736b731f는 같은 오류 RED→GREEN13 및 필수CI5개 성공(관리자691·backend2184PASS/기존2SKIP) 후 병합됐지만 새 UI/gateway2산출물 정상·ARM native·공개 adopt/verify 후 실제 upstream 최종 QA를 통과했다. 실제 b750 backend의 같은4개 주유소 범위에서 줌9 집계→줌10 개별4개/누락·truncation 없음은04:23:36UTC 공개 BFF2요청으로 확인했다. 수정 UI는5폭·위치 이동/거절·실제 카메라 줌10·주유소/이력 차트·터치·실제 VWorld5타일 decode·pageerror0건을 통과했다. 별도 공개 HTTPS 검증에서 지도와 API 상태가 200을 반환했다. 모바일 390px에서 제목과 메뉴가 없고 줌 10에 집계 없이 주유소 300건이 표시됐다. |
| Geo | PR #651 `8260e357` API·코드 서버의 정상 ARM 이미지와 Manager 적용 확인. 실행 설정 6개 복원 및 설치 분포 62/103 검증 | PR #650의 `3589972dd734` 관리 UI를 별도로 빌드·교체했다. 이미지 `sha256:51f847628f7e9ef15d5`, Node 26.13.1, PC 1280px·모바일 390px 제목·표·인증 검사 통과. API·코드 서버·DB 컨테이너와 UI 환경값이 배포 전후 동일하다. 이후 `500c84797b00`의 관리 UI 이미지 `sha256:62109ca7f6cd9b909d6b`만 다시 적용했다. ARM 및 PC 1280px·모바일 390px 화면과 보호 경로를 다시 검증했다. 이전 UI에서 실시한 5폭·18타일 검증은 당시 이미지의 근거로 보존한다. |
| Pinvi | PR791716781d0의 본 작업 API/CS 정상/native·SDK626·원13개 복원·웹5폭/지도/인증 수용 완료 | 이후 다른 작업이 같은716소스로 재빌드한 현재API2e62713a/CSec02765b/UI073cfedb의 설치65/78분포·VCS·CommonPY19파일·UI121파일·Node26을 대조했다. 공개adopt/verify로 Pinvi CURRENT를 실제tuple과 맞췄고 현재1280에서 실제4타일·로그인/줌·로그아웃401·오류0건을 확인했다. 과거5폭은 이전tuple의 역사이며 native 모바일 실기기·EAS·스토어 미실행 |
| Concierge | PR2799e266814 API/MCP·CS 정상/native·공식4역할 SDK626·원3개 sensor 복원·인증/MCP metadata 수용 | UI039c445a/imageb4d533cc 재사용. 이후 다른 작업의 CS 재기동은 같은 이미지이며 실제 provider/tool 실행을 새로 하지 않음 |
| Manager | PR627db78d1a8 양 호스트 실제 정상 설치·77모듈/28공유분포/pipcheck·로그인/로그아웃/재사용401 수용 완료. 전체CI4468PASS | 실제 동일 code bytes의30330 producer wheel을 재사용하고627로 재포장하지 않음. UI7f07a171·Node26.13.1 유지. Fuel 별도 target 및2컨테이너 등록 실제 동작 확인 |
| Map | Claude 담당으로 읽기 전용 통합 기록만 확인. 자연02:30 적재 시 다른 작업의01b602e 소스가 실제 실행됨 | 이번 작업이 Map source·이미지를 변경하지 않음. 다른 source/부하의 적재 표본을 Weather 속도 개선율로 비교하지 않음 |

## CI 실패를 조기에 확인하는 순서

| 프로젝트 | 실제 실행 순서와 조정 결과 | 근거 |
|---|---|---|
| Geo | Common 웹 guard와 OpenAPI는 독립 실행한다. Python 정책이 끝난 뒤 백엔드·PostGIS·Dagster를 병렬로 시작한다. PR CI에서 정책 완료 후 세 작업이 2–3초 뒤 시작했다. | [PR #653](https://github.com/digitie/kor-travel-geo/pull/653) · [검증 실행](https://github.com/digitie/kor-travel-geo/actions/runs/44840179735) |
| Transport | Common 웹 guard 뒤 공개·관리 웹이 병렬 실행한다. 공개 웹 런타임 계약 19건을 npm 설치 전에 실행한다. 이전 CI에서 뒤따르는 설치·검사에 약 86초가 걸렸다. | [PR #236](https://github.com/digitie/kor-travel-transport/pull/236) · [검증 실행](https://github.com/digitie/kor-travel-transport/actions/runs/44840343022) |
| Weather | Python 정책 뒤 Python 검사를 실행한다. 웹은 Common guard, 정적 검사·단위 테스트·빌드, Playwright 순서다. headless shell로 fixture 34건과 타일 5건을 유지한다. | [PR #280](https://github.com/digitie/kor-travel-weather/pull/280) · [검증 실행](https://github.com/digitie/kor-travel-weather/actions/runs/44840934957) |
| Concierge | 웹 정적 검사·단위 테스트·빌드 뒤 브라우저 회귀 17건을 실행한다. 기본 Chromium headless 프로젝트에 필요한 shell만 내려받는다. | [PR #281](https://github.com/digitie/kor-travel-concierge/pull/281) · [검증 실행](https://github.com/digitie/kor-travel-concierge/actions/runs/44841095023) |
| Pinvi | 웹 선행 검사는 lockfile·Common·Doctor·lint·typecheck 뒤 웹 빌드·이미지·E2E에 연결된다. 모바일은 lockfile 직후 스타일 계약을 검사한다. 기존 실패 두 건에서는 앞선 npm 설치에 28–36초를 사용했다. | [PR #793](https://github.com/digitie/pinvi/pull/793) · [검증 실행](https://github.com/digitie/pinvi/actions/runs/44840388515) |
| Common | 비밀 값·버전 정책이 문서·도구·패키지의 선행 조건이다. 문서 job은 소스 SHA 직후 공백을 검사하고 Python·Node 설치를 시작한다. | [PR #77](https://github.com/digitie/kor-travel-common/pull/77) · [검증 실행](https://github.com/digitie/kor-travel-common/actions/runs/44840180300) |
| Manager | 별도 Common 웹·Python 정책과 제품 검사를 병렬 실행한다. 웹은 빌드 통과 후 Chromium을 설치한다. 백엔드 21분 8초 중 pytest가 20분 45초였다. 현재 순서를 유지했다. | [검증 실행](https://github.com/digitie/kor-travel-docker-manager/actions/runs/44646286987) |
| Map | Claude 담당 실행을 읽기 전용으로 비교했다. PostGIS 통합은 단위 행렬 성공 뒤 시작하며 lint·이미지·프런트엔드·fixture는 독립 실행한다. | [검증 실행](https://github.com/digitie/kor-travel-map/actions/runs/44833958026) |

Weather와 Concierge는 직전 실행마다 일반 Chromium 197.8 MiB를 별도로 받았다. 두 변경은 해당 다운로드만 줄이고 시스템 의존성과 브라우저 검사를 유지한다. 이번 CI 조정은 배포와 실제 화면 확인 뒤 진행했다.

## 의존성 정렬값과 실제 사용 범위

아래 값은 목표 source/lock의 비교다. 위 운영 표의 완료 여부를 대신하지 않는다. D는 직접 선언, T는 해당 표면의 잠금 그래프에서 도달, L은 공유 lock에만 존재, —는 부재다. G/W/Tp/Ta/Pw/Pm/M/C는 각각 Geo/Weather/Transport공개/Transport관리자/Pinvi웹/Pinvi모바일/Manager/Concierge다. Node/npm 목표는 여덟 표면 모두26.13.1/12.0.1이다. Manager 양 호스트 UI도 이 값으로 실제 교체·화면 수용을 완료했다.

PostCSS는 Geo·Manager의 Next 내부8.5.23을 루트8.5.32로 정렬한다. geojson-vt는 이미6.3.1인 Concierge를 기준으로 다른 실제 지도 소비자의 허용 범위 내6.3.1을 고정한다. 두 변경 모두 root override와 lock을 함께 고정해 이후 npm update의 우연한 재선택을 막는다. Common tgz bytes·다른 패키지 버전은 바꾸지 않는다. RN11.5.1이 정확히 요구하는 style-spec26.4.4와 JS GL의26.6.0 공존은 호환성에 따른 구분이다.

### 목표 소스의 주요 버전 행렬

| 라이브러리 | G | W | Tp | Ta | Pw | Pm | M | C |
|---|---|---|---|---|---|---|---|---|
| `react` | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 |
| `react-dom` | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 | D 19.3.1 |
| `next` | D 16.4.6 | D 16.4.6 | D 16.4.6 | D 16.4.6 | D 16.4.6 | L | D 16.4.6 | D 16.4.6 |
| `tailwindcss` | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 |
| `@tailwindcss/postcss` | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 | D 4.3.5 |
| `eslint` | D 10.14.0 | D 10.14.0 | D 10.14.0 | D 10.14.0 | D 10.14.0 | D 10.14.0 | D 10.14.0 | D 10.14.0 |
| `react-doctor` | D 0.9.22 | D 0.9.22 | D 0.9.22 | D 0.9.22 | D 0.9.22 | D 0.9.22 | D 0.9.22 | D 0.9.22 |
| `@tanstack/react-table` | D 9.3.1 | T 9.3.1 | T 9.3.1 | T 9.3.1 | D 9.3.1 | L | T 9.3.1 | T 9.3.1 |
| `@tanstack/react-virtual` | D 3.14.26 | T 3.14.26 | T 3.14.26 | T 3.14.26 | D 3.14.26 | L | T 3.14.26 | T 3.14.26 |
| `@tanstack/react-query` | D 5.107.1 | D 5.107.1 | — | — | D 5.107.1 | D 5.107.1 | D 5.107.1 | D 5.107.1 |
| `radix-ui` | D 1.8.1 | T 1.8.1 | T 1.8.1 | T 1.8.1 | T 1.8.1 | L | T 1.8.1 | T 1.8.1 |
| `@radix-ui/react-focus-scope` | D 1.3.1+kortravel.fix.2 | D 1.3.1+kortravel.fix.2 | D 1.3.1+kortravel.fix.2 | D 1.3.1+kortravel.fix.2 | D 1.3.1+kortravel.fix.2 | L | D 1.3.1+kortravel.fix.2 | D 1.3.1+kortravel.fix.2 |
| `zod` | D 4.6.7 | D 4.6.7 | D 4.6.7 | D 4.6.7 | D 4.6.7 | D 4.6.7 | D 4.6.7 | D 4.6.7 |
| `react-hook-form` | D 7.92.0 | D 7.92.0 | D 7.92.0 | D 7.92.0 | D 7.92.0 | D 7.92.0 | D 7.92.0 | D 7.92.0 |
| `@hookform/resolvers` | D 7.0.5 | D 7.0.5 | T 7.0.5 | T 7.0.5 | D 7.0.5 | L | T 7.0.5 | D 7.0.5 |
| `pretendard` | D 1.3.9 | D 1.3.9 | D 1.3.9 | D 1.3.9 | D 1.3.9 | D 1.3.9 | D 1.3.9 | D 1.3.9 |
| `zustand` | D 5.1.0 | D 5.1.0 | D 5.1.0 | D 5.1.0 | D 5.1.0 | D 5.1.0 | D 5.1.0 | D 5.1.0 |
| `@kor-travel/ui` | D 0.2.3 | D 0.2.3 | D 0.2.3 | D 0.2.3 | D 0.2.3 | L | D 0.2.3 | D 0.2.3 |
| `@kor-travel/tokens` | D 0.1.4 | D 0.1.4 | D 0.1.4 | D 0.1.4 | D 0.1.4 | D 0.1.4 | D 0.1.4 | D 0.1.4 |
| `@kor-travel/toast` | D 0.1.3 | — | — | — | — | — | — | — |
| `typescript` | D 5.9.3 | D 5.9.3 | D 5.9.3 | D 5.9.3 | D 5.9.3 | D 5.9.3 | D 5.9.3 | D 5.9.3 |
| `postcss` | D 8.5.32 | D 8.5.32 | D 8.5.32 | T 8.5.32 | D 8.5.32 | D 8.5.32 | D 8.5.32 | D 8.5.32 |
| `tailwind-merge` | D 3.7.0 | D 3.7.0 | T 3.7.0 | D 3.7.0 | D 3.7.0 | L | T 3.7.0 | D 3.7.0 |
| `lightningcss` | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 | D 1.33.0+nativecss.fix.4 |

7개 웹 표면에서 Next16.4.6, Tailwind4.3.5, ESLint10.14.0, ReactDoctor0.9.22 및 실제 사용 Common UI0.2.3가 일치한다. React/ReactDOM19.3.1·tokens0.1.4은 모바일까지 일치한다. Table9.3.1·Virtual3.14.26·Query5.107.1·Zod4.6.7·RHF7.92.0·resolver7.0.5·Pretendard1.3.9·Zustand5.1.0도 사용되는 표면 사이에서 버전이 같다. 직접 선언과 전이 도입 여부는 다르다.

### Floating·Radix

| 라이브러리 | G | W | Tp | Ta | Pw | Pm | M | C |
|---|---|---|---|---|---|---|---|---|
| `@floating-ui/react` | — | — | — | — | — | — | — | — |
| `@floating-ui/react-dom` | T 2.1.9 | T 2.1.9 | T 2.1.9 | T 2.1.9 | T 2.1.9 | L | T 2.1.9 | T 2.1.9 |
| `@floating-ui/dom` | T 1.8.0 | T 1.8.0 | T 1.8.0 | T 1.8.0 | T 1.8.0 | L | T 1.8.0 | T 1.8.0 |
| `@floating-ui/core` | T 1.8.0 | T 1.8.0 | T 1.8.0 | T 1.8.0 | T 1.8.0 | L | T 1.8.0 | T 1.8.0 |
| `@floating-ui/utils` | T 0.2.12 | T 0.2.12 | T 0.2.12 | T 0.2.12 | T 0.2.12 | L | T 0.2.12 | T 0.2.12 |
| `@radix-ui/react-dialog` | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | L | T 1.3.1 | T 1.3.1 |
| `@radix-ui/react-dropdown-menu` | T 2.2.1 | T 2.2.1 | T 2.2.1 | T 2.2.1 | T 2.2.1 | L | T 2.2.1 | T 2.2.1 |
| `@radix-ui/react-popover` | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | L | T 1.3.1 | T 1.3.1 |
| `@radix-ui/react-select` | T 2.4.1 | T 2.4.1 | T 2.4.1 | T 2.4.1 | T 2.4.1 | L | T 2.4.1 | T 2.4.1 |
| `@radix-ui/react-toast` | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | L | T 1.3.1 | T 1.3.1 |
| `@radix-ui/react-tooltip` | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | L | T 1.4.1 | T 1.4.1 |

Floating의 서로 다른 패키지를 같은 버전 번호로 맞추지 않는다. 현재 웹의 react-dom2.1.9·dom/core1.8.0·utils0.2.12는 동일한 조합이고 `@floating-ui/react`는 전부 없다. Radix 개별60종의 전체 버전 벡터는 모든 실제 사용 표면에서 일치하며 아래 추가 표까지 이 문서에 모두 담았다. 패치 FocusScope는 1.3.1+kortravel.fix.2다.

### 모바일·지도

| 라이브러리 | G | W | Tp | Ta | Pw | Pm | M | C |
|---|---|---|---|---|---|---|---|---|
| `nativewind` | — | — | — | — | L | D 5.0.0-rc.1 | — | — |
| `react-native` | — | — | — | — | L | D 0.88.1 | — | — |
| `expo` | — | — | — | — | L | D 58.0.26 | — | — |
| `expo-router` | — | — | — | — | L | D 58.0.32 | — | — |
| `react-native-css` | — | — | — | — | L | D 3.1.0-rc.1 | — | — |
| `react-native-reanimated` | — | — | — | — | L | D 4.7.1 | — | — |
| `react-native-worklets` | — | — | — | — | L | D 0.13.1 | — | — |
| `maplibre-gl` | D 6.17.0 | D 6.17.0 | — | D 6.17.0 | D 6.17.0 | T 6.17.0 | — | D 6.17.0 |
| `@maplibre/maplibre-react-native` | — | — | — | — | L | D 11.5.1 | — | — |
| `vworld-map-core` | D 1.0.1 | D 1.0.1 | — | D 1.0.1 | D 1.0.1 | D 1.0.1 | — | D 1.0.1 |
| `vworld-map-web` | D 1.0.4 | D 1.0.4 | — | D 1.0.4 | D 1.0.4 | D 1.0.4 | — | D 1.0.4 |
| `vworld-map-rn` | — | — | — | — | L | D 1.0.2 | — | — |
| `maplibre-vworld-react` | — | — | — | — | — | — | — | — |
| `@maplibre/geojson-vt` | T 6.3.1 | T 6.3.1 | — | T 6.3.1 | T 6.3.1 | T 6.3.1 | — | T 6.3.1 |
| `@maplibre/maplibre-gl-style-spec` | T 26.6.0 | T 26.6.0 | — | T 26.6.0 | T 26.6.0 | T 26.4.4/26.6.0 | — | T 26.6.0 |

Pinvi 모바일의 NativeWind **5.0.0-rc.1**, RN0.88.1, Expo58.0.26, Expo Router58.0.32는 현재 소스의 확정 값이다. RC라는 표기를 유지하며 registry 최신·안정 버전이라는 판단은 하지 않는다. 모바일에는 Common tokens만 직접 선언되고 웹 UI·Radix·Floating·Table/Virtual은 공유 lock의 L이다. 모바일 manifest는 vworld-map-web도 직접 선언하므로 MapLibre GL JS가 T로 도달하지만 이것만으로 네이티브 실행 시 JS 지도가 로드된다고 단정하지 않는다.



### 나머지 비교 패키지

아래는 앞 표에 중복하지 않은 55개다. 앞 표와 합쳐 비교 대상으로 지정한105개 이름의 source/lock 결과를 이 단일 문서에 모두 기록한다. 이는 npm 전체 전이 그래프의 모든 이름이나 registry 최신성 검증을 뜻하지 않는다. D/T/L 구분과 실제 적용 여부는 앞의 정의를 따른다.

| 라이브러리 | G | W | Tp | Ta | Pw | Pm | M | C |
|---|---|---|---|---|---|---|---|---|
| `@maplibre/mlt` | T 1.3.0 | T 1.3.0 | — | T 1.3.0 | T 1.3.0 | T 1.3.0 | — | T 1.3.0 |
| `@maplibre/vt-pbf` | T 4.3.3 | T 4.3.3 | — | T 4.3.3 | T 4.3.3 | T 4.3.3 | — | T 4.3.3 |
| `@radix-ui/number` | T 1.1.3 | T 1.1.3 | T 1.1.3 | T 1.1.3 | T 1.1.3 | L 1.1.3 | T 1.1.3 | T 1.1.3 |
| `@radix-ui/primitive` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-accessible-icon` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | L 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-accordion` | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | L 1.3.1 | T 1.3.1 | T 1.3.1 |
| `@radix-ui/react-alert-dialog` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-arrow` | T 1.1.17 | T 1.1.17 | T 1.1.17 | T 1.1.17 | T 1.1.17 | L 1.1.17 | T 1.1.17 | T 1.1.17 |
| `@radix-ui/react-aspect-ratio` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | L 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-avatar` | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | T 1.3.1 | L 1.3.1 | T 1.3.1 | T 1.3.1 |
| `@radix-ui/react-checkbox` | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | L 1.4.1 | T 1.4.1 | T 1.4.1 |
| `@radix-ui/react-collapsible` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-collection` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-compose-refs` | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 |
| `@radix-ui/react-context` | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 |
| `@radix-ui/react-context-menu` | T 2.4.1 | T 2.4.1 | T 2.4.1 | T 2.4.1 | T 2.4.1 | L 2.4.1 | T 2.4.1 | T 2.4.1 |
| `@radix-ui/react-direction` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-dismissable-layer` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-focus-guards` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | L 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-form` | T 0.3.0 | T 0.3.0 | T 0.3.0 | T 0.3.0 | T 0.3.0 | L 0.3.0 | T 0.3.0 | T 0.3.0 |
| `@radix-ui/react-hover-card` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-id` | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 |
| `@radix-ui/react-label` | T 2.1.17 | T 2.1.17 | T 2.1.17 | T 2.1.17 | T 2.1.17 | L 2.1.17 | T 2.1.17 | T 2.1.17 |
| `@radix-ui/react-menu` | T 2.2.1 | T 2.2.1 | T 2.2.1 | T 2.2.1 | T 2.2.1 | L 2.2.1 | T 2.2.1 | T 2.2.1 |
| `@radix-ui/react-menubar` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-navigation-menu` | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | L 1.4.1 | T 1.4.1 | T 1.4.1 |
| `@radix-ui/react-one-time-password-field` | T 0.2.1 | T 0.2.1 | T 0.2.1 | T 0.2.1 | T 0.2.1 | L 0.2.1 | T 0.2.1 | T 0.2.1 |
| `@radix-ui/react-password-toggle-field` | T 0.2.1 | T 0.2.1 | T 0.2.1 | T 0.2.1 | T 0.2.1 | L 0.2.1 | T 0.2.1 | T 0.2.1 |
| `@radix-ui/react-popper` | T 1.4.0 | T 1.4.0 | T 1.4.0 | T 1.4.0 | T 1.4.0 | L 1.4.0 | T 1.4.0 | T 1.4.0 |
| `@radix-ui/react-portal` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | L 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-presence` | T 1.1.11 | T 1.1.11 | T 1.1.11 | T 1.1.11 | T 1.1.11 | T 1.1.11 | T 1.1.11 | T 1.1.11 |
| `@radix-ui/react-primitive` | T 2.2.0 | T 2.2.0 | T 2.2.0 | T 2.2.0 | T 2.2.0 | T 2.2.0 | T 2.2.0 | T 2.2.0 |
| `@radix-ui/react-progress` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-radio-group` | T 1.5.1 | T 1.5.1 | T 1.5.1 | T 1.5.1 | T 1.5.1 | L 1.5.1 | T 1.5.1 | T 1.5.1 |
| `@radix-ui/react-roving-focus` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-scroll-area` | T 1.4.0 | T 1.4.0 | T 1.4.0 | T 1.4.0 | T 1.4.0 | L 1.4.0 | T 1.4.0 | T 1.4.0 |
| `@radix-ui/react-separator` | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | T 1.2.0 | L 1.2.0 | T 1.2.0 | T 1.2.0 |
| `@radix-ui/react-slider` | T 1.6.1 | T 1.6.1 | T 1.6.1 | T 1.6.1 | T 1.6.1 | L 1.6.1 | T 1.6.1 | T 1.6.1 |
| `@radix-ui/react-slot` | T 1.5.0 | T 1.5.0 | T 1.5.0 | T 1.5.0 | T 1.5.0 | T 1.5.0 | T 1.5.0 | T 1.5.0 |
| `@radix-ui/react-switch` | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | T 1.4.1 | L 1.4.1 | T 1.4.1 | T 1.4.1 |
| `@radix-ui/react-tabs` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-toggle` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-toggle-group` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-toolbar` | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | T 1.2.1 | L 1.2.1 | T 1.2.1 | T 1.2.1 |
| `@radix-ui/react-use-callback-ref` | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 |
| `@radix-ui/react-use-controllable-state` | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 | T 1.3.0 |
| `@radix-ui/react-use-effect-event` | T 0.0.5 | T 0.0.5 | T 0.0.5 | T 0.0.5 | T 0.0.5 | T 0.0.5 | T 0.0.5 | T 0.0.5 |
| `@radix-ui/react-use-escape-keydown` | T 1.1.6 | T 1.1.6 | T 1.1.6 | T 1.1.6 | T 1.1.6 | L 1.1.6 | T 1.1.6 | T 1.1.6 |
| `@radix-ui/react-use-is-hydrated` | T 0.1.3 | T 0.1.3 | T 0.1.3 | T 0.1.3 | T 0.1.3 | T 0.1.3 | T 0.1.3 | T 0.1.3 |
| `@radix-ui/react-use-layout-effect` | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 |
| `@radix-ui/react-use-previous` | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | L 1.1.4 | T 1.1.4 | T 1.1.4 |
| `@radix-ui/react-use-rect` | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | T 1.1.4 | L 1.1.4 | T 1.1.4 | T 1.1.4 |
| `@radix-ui/react-use-size` | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | T 1.1.5 | L 1.1.5 | T 1.1.5 | T 1.1.5 |
| `@radix-ui/react-visually-hidden` | T 1.2.13 | T 1.2.13 | T 1.2.13 | T 1.2.13 | T 1.2.13 | L 1.2.13 | T 1.2.13 | T 1.2.13 |
| `@radix-ui/rect` | T 1.1.3 | T 1.1.3 | T 1.1.3 | T 1.1.3 | T 1.1.3 | L 1.1.3 | T 1.1.3 | T 1.1.3 |


## 불변 산출물과 상류 출처

현재 UI0.2.3/tokens0.1.4/선택형toast0.1.3 정본의 producer는 0e2a3f5aa16323df0d009360802661c9bc496dc6, guard/catalog은 d644632ea9eaf2f6b6baa49305d65fae5bbc0bd4다. producer artifact14500111373 ZIP SHA256은19881f2c3ed598ed7ec213c559be21ece2be77068bddee6de5bd249b6f8019e1이다. 같은 공개 버전을 재포장하지 않았다.

| 패키지 | 버전 | tgz SHA256 | 정규 파일 수 |
| --- | --- | --- | --- |
| @kor-travel/ui | 0.2.3 | aa19793165ae37b2214d210692e23235545e1464c4e0059f99d943411fa753d9 |96 |
| @kor-travel/tokens |0.1.4 |33d08d7b37c60d3e319da19608ce05137f6bf587dc8d42e3ce0dfb4b597a61fc |25 |
| @kor-travel/toast |0.1.3 |34b514b270f88fc19c6b411b975d4497f91f3581530f32a39be264874ca09b37 |8 |

웹은121개, Toast도 사용하는 Geo는129개, 모바일은 tokens25개 파일을 대조한다. 도달하지 않는 workspace lock의 DOM 라이브러리를 모바일 runtime 적용으로 세지 않는다.

VWorld core1.0.1/web1.0.4/rn1.0.2는 GitHub 상류79b70997de8dd4a6bcc9630233f14f273cb27991의 산출물이다. 옛 private mono-root maplibre-vworld-react 직접 설치와 source alias는 금지하고 공개 core/web/RN pack을 사용한다. MapLibre GL6.17.0/RN11.5.1은 별개의 패키지다.

FocusScope1.3.1+kortravel.fix.2는 상류 fork1752a539c8d5ae57961a0fa2702d2573d48fefe7, lightningcss1.33.0+nativecss.fix.4는 원본1e94372a6da4a55eac4a6dc3ff9cdeec103e8ac1에서 재현 결함을 고친 결과다. 앱 자체 레이어로 같은 결함을 반복 우회하지 않는다. ARM WASM/JS adapter와 GNU ELF는 플랫폼별 산출물로 검증한다.

## 재발 방지

Common versions.json과 자동 생성 frontend-dependencies.json이 정확 버전·프로필을 소유한다. 각 소비자는 check:dependencies와 불변 SHA에 고정한 reusable guard로 manifest·lock·vendor·common-artifacts.json·SRI·도달한 실제 설치 그래프를 비교한다. caller uses와 common-ref는 같은40자리 SHA여야 한다. 자체 vendor/원장/lock을 함께 바꿔 로컬 검사만 통과하는 차이도 중앙 정본 대조로 차단한다.

표·Base UI/Floating UI 직접 구현, private 지도 source alias의 재도입은 source AST guard가 검사한다. 동적인 모든 UI 동작을 정적으로 증명하는 것은 아니므로 공통 공개 API 계약과 실제 소비 화면 검증을 함께 유지한다. 로컬 Next cache는 앱별로, wheel은 Python ABI·glibc·GDAL별로 분리한다. 변경 없는 정상 UI/Python 이미지의 원래 source·ID를 보존하고 새 source로 재라벨하지 않는다.

Common76의 USED Python 정책에는 application 149개와 명시적 build tool 3개의 정확 축이 있다. MCP의 정확 동반 배포 mcp-types도 application 축에 포함한다. 미사용 패키지를 강제 설치하지 않으며 host daemon pool과 앱 의존성을 같은 축으로 취급하지 않는다. Python package bytes producer와 정책 commit도 별도로 기록한다.

## 성능 검증의 범위

Weather의 DB 전환·COPY·일반 예보 RR proof·보존 이력 조회·GC writer timeout 개선과 Transport의 stream/COPY는 각각 실제 계약·로컬 비교 또는 해당 배포 측정에 결박한다. 로컬 CPU 감소율을 운영 전체 속도 개선율로 바꾸지 않는다. 거절한 JOIN·FK generic plan·압축·cursor fraction 후보를 제품 개선 목록에 넣지 않는다.

Weather 첫 cold 응답의 driver 대기는 확인했지만 전체 SQL elapsed에는 네트워크·스케줄링이 포함된다. 5Hz thread sample 수를 request tick 수로 합산하지 않는다. production SELECT/DECLARE의 실제 계획은 같은 bounded PK ANY index 경로였으므로 cursor_tuple_fraction 변경 가설은 폐기했다. 로컬 fixture는 실제 child history 크기를 재현하지 못해 운영16초와 직접 비교할 수 없다.

자연02:30 적재 중 발생한503은 export_inventory_selection._active_scope_states의 attempt_id/run_id/status/owner_epochs 조회 statement_timeout이었다. 후속200 회복을 영구 해소로 처리하지 않는다. 기존 로컬 namespace를 실제 Psycopg3.3.9 binary·SQLAlchemy2.1.9 및886,894 attempt/545,845 generation/548,000 child/1,452위치로 구성했다. 실제 API·pool과 원래61초 lease 경과를 통해12회 조회 뒤 자동 prepared generic 선택·접근 경로 차이를 확인했고15,972항목/80페이지 walk에 중복이 없었다. 이는 동작 메커니즘 재현이며 지연 개선 증거는 아니다. 자연 prepared generic baseline과 scoped custom 후보를3쌍 비교했으나 전체 reader 중앙값676.044→670.546ms(0.813%)이고 세 번째 쌍은9.07% 느려졌다. 일관된 유의미 개선이 없어 후보를 폐기했으며 제품 patch/PR은 없다. 이 메커니즘을 운영503의 원인으로 확정하지 않는다.

자연05:30 적재는27.314초에200 응답5회로 성공했다. 사전 SQL guard 검증을 놓친 관찰 도구 오류로 핵심 구간 표본은0건이며, 뒤늦은 idle 표본94건을 원인 증거로 사용하지 않는다. 이후 관찰 준비를 실제 확인한 저장 데이터 SHORT 조회1회는200·16.469초였고 SQL10.021초/freeze12.096초였다. 같은 쿼리의 연속 구간6.037초에서 CPU0.830초·실행 대기3.835초·프로세스에 부과된 저장소 읽기 약24.3MB를 관찰했다. 관찰한 scope plan 쿼리는 수동 GET보다 먼저 시작했으므로 모든 표본을 그 요청 단독 비용으로 귀속하지 않는다. DataFileRead와 실행 대기가 함께 있어 단순 디스크 병목이나 특정 경쟁 프로세스로 확정하지 않으며, 이 관찰은503 영구 해소 증거가 아니다.

기동 시 한 번 읽는 실험에서 현재 관측은 동일 키의 두 번째 HTTP 200에 35회 대신 4회 SQL을 실행했고, 캐시 만료 후 다시 생성했다. 단기예보 두 요청은 승인 검증과 본문 읽기를 각각 수행했다. 발행 대기 조회는 후보별 유일 키 조회로 바꿔 129행의 중간 페이지가 로컬 auto 계획에서 567ms에서 11ms로 줄었다. 운영 적용 후 발행 센서의 정기 실행 두 건에서 대기 조회 구간은 7.4초와 7.7초였고 각각 27건과 36건을 발행했다. 첫 단기예보 진단은 HTTP 200, 5.790초였고 SQL 2.145초, freeze 4.385초였다. 11월 21일 08:30 KST 정기 소비와 일치한 Weather SHORT 접근 로그 47건은 모두 200이었다. 해당 관측 구간 SHORT 503은 0건이었다. 503 재발률과 신선도는 추가 운영 표본이 필요하다. [Weather PR #279](https://github.com/digitie/kor-travel-weather/pull/279)

## 남은 완료 조건

Transport 공식 적용과 Fuel 내부·공개 경로 검증을 완료했다. 별도 공개 HTTPS 검증에서 지도와 API 상태가 200을 반환했다. 모바일 390px에서 제목과 메뉴가 없고 줌 10에 집계 없이 주유소 300건이 표시됐다. 후속 Fuel 웹 `2ed65d8d`은 위치 버튼을 44×44px 아이콘으로 표시한다. 실제 390px·1280px에서 위치 권한 허용 후 조회와 전체 화면을 확인했다. [Transport PR #235](https://github.com/digitie/kor-travel-transport/pull/235)

Weather 단기예보는 새 이미지의 첫 진단에서 200을 반환했다. 503 재발률과 신선도는 후속 운영 지표로 확인한다.

## 구체적으로 바뀐 구현과 검증

| 구현 | 동작과 근거 | 남아 있는 범위 |
| --- | --- | --- |
| Weather 파일→DB | 기존 파일을 DB artifact로 backfill하고 coverage·SHA·byte·point count를 검증한 뒤 정리했다. 이후 정상 배포에서 legacy 파일 재읽기·backfill·같은 DDL을 반복하지 않는다 | DB reader의 첫 요청 속도와 원천 최신성은 별도 미해결 항목 |
| Weather 페이지 입력 상한 | prefetch·fallback까지 페이지 누적 입력8MiB를 적용하고, 아직 읽지 않은 ref 이전 cursor를 보존한다. 전체 walk SHA 동등성과7개 RED 회귀를 확인했다 | 응답 body 크기와 DB에서 검증한 입력 bytes는 다르다. 과거 약125MB 전역 증가를 요청 단독 값으로 바꾸지 않는다 |
| Weather 저장·조회 | 같은 트랜잭션의 COPY와 RR proof 및 보존 이력 조회를 개선했다. 최종 로컬 전체 ingest는3.055→2.426초였고62개 의미 계약을 통과했다 | 로컬 비교를 전체 자연 수집 wall-time이나 운영 cold 개선율로 주장하지 않는다 |
| Weather GC | 실제 보존 경쟁을 재현해 writer lock timeout1→5초를 적용했다. GC1.36초 사례와 기능 계약을 확인했다 | 이것이 모든 과거503의 원인이라는 결론은 아니다. 현재 source도STALE |
| Transport rail | ORM 재조립 대신 같은 세션의 Core stream, 이후400행 단위 asyncpg COPY를 사용한다. 본문·ETag·14개 guard를 유지했고 로컬1466행570.498→389.773ms,4000행1216.212→872.192ms였다 | 최신 운영 첫 진단은 200·7,766ms, 조건부는 304·305ms였다. 단일 표본으로 기록한다 |
| Transport 저장 유가 reader | 기존 DB의 주유소·통계·이력을 읽는 전용 공개 BFF/gateway를 만들었다. 유가 지도는 줌10부터 상세화하고 같은 좌표의 주유소 선택 기능을 유지한다 | PR231 소스/CI/fixture 검증과 실제 서비스 수용을 구분한다 |
| Opinet CDP 종료 경쟁 | pending Fetch 실패 처리를 drain한 뒤 Fetch.disable하는 순서와 기존 조기 오류 거부를 라이브러리 원본에서 수정했다. 실제 Chromium resource-policy 경쟁 시험과 consumer pin을 검증했다 | 과거95분 실패 run의 전체 성공을 새 자연 run 없이 단정하지 않는다 |
| npm cache | BusyBox cp -a -n의 exit0/내용 미복사 문제를 재현하고 npm12 cacache API로 교체했다.495개 key/info/content/streamed SHA512를 검산했다 | 공개 tarball 재사용이며 모든 앱 전체 offline 설치를 보장하는 증거는 아니다 |
| GDAL·wheel·Next cache | GDAL을 프로젝트 COPY보다 앞에 두고 ABI·glibc·GDAL별 wheel cache와 앱별 Next cache를 쓴다. Geo API→CS의 Fiona1.10.1 wheel 재사용, Transportb750의 GDAL·앱 의존성·Chromium layer CACHED를 실제 확인했다. 실제 GDAL은 Geo3.10.3/Transport3.13.3으로 다르며 ABI별 캐시를 분리한다 | 캐시 설정·예상 hit와 실제 로그를 구분한다. 전체 build/export 비용을 GDAL 재컴파일로 설명하지 않는다 |
| 공통 UI | VirtualTable의 정렬·가상화·스크롤·접근성, Radix overlay와 포커스, PC 세로 rail/모바일 drawer를 공통화했다. 앱 경로·인증·도메인 상태는 앱 소유로 둔다 | 공개 Fuel 지도는 사용자 지시에 따라 AdminShell/제목/메뉴를 생략한다. native 모바일 DOM UI는 강제하지 않는다 |
| 재발 방지 | 정확 버전·동일 bytes·SRI·Node/npm·실제 도달 그래프와 금지 자체 구현을 로컬 및 immutable reusable guard로 검사한다. Python도 actual-used 교집합과 명시적 build tool을 검사한다 | 정적 검사·CI·정규 이미지·native·실제 화면 수용을 각각 기록했다. CI 검사 순서와 실측 근거는 위 표에 적었다 |

이전110분 Transport 빌드에서 Next2개46.1분·export3개31.4분·npm2개16.7분·node_modules 복사4.9분이99.1분을 차지했다. 해당 빌드도14단계와 GDAL이CACHED였다. 다른 source·부하·온도인 표본의 직접 개선율로 바꾸지 않으며, export 내부 tar/import는 중첩하므로 중복 합산하지 않는다.

Transport 관리자의 로컬 @kor-travel/parking-ui는 file:../../../frontend/src와 install-links=true로 복사 설치된다. 따라서 shared source 변경이 npm ci 레이어를 무효화하는 것은 설치본 갱신에 필요하다. 단순 COPY 순서 이동 후보는 폐기했다. 외부 패키지와 로컬 패키지 설치를 분리하는 후속 최적화에는 실제 설치 bytes와 삭제 반영 동등성 검증이 필요하며, 이번 배포 코드에는 추가하지 않았다. 해당 b750 설치 단계는656.4초였고 전체 frontend 빌드 시간과 구분한다.

운영 바이너리 버전은 별도로 읽는다. 실제 Pinvi Python3.12.14와 Transport3.12.16, Geo GDAL3.10.3과 Transport3.13.3 차이가 있다. 아래149 application exact를 인터프리터·OS native 전체 동일성으로 확대하지 않는다. Transport 관리자는 기존8시간 서명쿠키 방식으로 일반 로그아웃 뒤 쿠키 없는 보호 경로401을 확인했으며, 복사한 미만료 쿠키의 서버 회수는 기존에 구현되지 않았다. 지역 카드 수정 전후4개 인증 파일은 동일하고, 이번 공개 Fuel 작업에 인증 방식 교체를 추가하지 않았다.

## Python 공통 사용 교집합의 정확 버전

정본 Common76 f7017c63a332b58365ff3ce1976de9e2cc452a2e의 versions.json application/buildTool에서 추출했다. 아래는 설치 의무 목록이나 모든 앱의 runtime 존재 증거가 아니다. 각 앱이 실제 사용하는 이름에 exact를 적용하며, 설치·사용 여부는 해당 normal/native 영수증으로 확인한다. 호스트 daemon 공유 호환성과 앱 runtime를 구분한다.

| 패키지 | application exact |
| --- | --- |
| alembic | 1.20.1 |
| annotated-doc | 0.0.7 |
| annotated-types | 0.8.0 |
| antlr4-python3-runtime | 4.13.2 |
| anyio | 4.16.0 |
| apscheduler | 3.11.3 |
| ast-serialize | 0.13.1 |
| asyncpg | 0.32.0 |
| attrs | 26.1.0 |
| av | 19.0.2 |
| backoff | 2.2.1 |
| boto3 | 1.44.7 |
| botocore | 1.44.7 |
| certifi | 2026.10.23 |
| cffi | 2.1.1 |
| charset-normalizer | 3.5.2 |
| click | 8.5.1 |
| colorama | 0.4.6 |
| coloredlogs | 14.0 |
| cryptography | 50.0.2 |
| ctranslate2 | 4.9.0 |
| dagster | 1.13.24 |
| dagster-graphql | 1.13.24 |
| dagster-pipes | 1.13.24 |
| dagster-postgres | 0.29.24 |
| dagster-shared | 1.13.24 |
| defusedxml | 0.7.1 |
| docker | 7.2.0 |
| docstring-parser | 0.18.0 |
| fastapi | 0.165.0 |
| faster-whisper | 1.2.1 |
| ffmpeg-python | 0.2.0 |
| filelock | 4.2.12 |
| flatbuffers | 25.12.19 |
| fsspec | 2026.9.0 |
| future | 1.0.0 |
| geoalchemy2 | 0.21.0 |
| google-ai-generativelanguage | 0.12.1 |
| google-api-core | 2.44.0 |
| google-api-python-client | 2.202.0 |
| google-auth | 2.62.2 |
| google-auth-httplib2 | 0.4.4 |
| google-generativeai | 0.8.6 |
| googleapis-common-protos | 1.76.0 |
| gql | 4.0.0 |
| graphene | 3.4.3 |
| graphql-core | 3.2.14 |
| graphql-relay | 3.2.0 |
| greenlet | 3.5.6 |
| grpcio | 1.85.3 |
| grpcio-health-checking | 1.81.2 |
| grpcio-status | 1.85.3 |
| h11 | 0.16.0 |
| hf-xet | 1.8.0 |
| httpcore | 1.0.9 |
| httpcore2 | 2.16.2 |
| httplib2 | 0.32.1 |
| httptools | 0.9.0 |
| httpx | 0.28.1 |
| httpx-sse | 0.4.3 |
| httpx2 | 2.16.2 |
| huggingface-hub | 2.4.0 |
| humanfriendly | 10.0 |
| idna | 3.20 |
| iniconfig | 2.3.1 |
| jinja2 | 3.1.6 |
| jmespath | 1.1.0 |
| jsonschema | 4.26.0 |
| jsonschema-specifications | 2025.9.1 |
| librt | 0.17.0 |
| mako | 1.4.3 |
| markdown-it-py | 4.3.0 |
| markupsafe | 3.0.4 |
| mcp | 2.3.0 |
| mcp-types | 2.3.0 |
| mdurl | 0.1.2 |
| multidict | 7.2.1 |
| mypy | 2.4.1 |
| mypy-extensions | 1.2.0 |
| numpy | 2.5.5 |
| onnxruntime | 1.32.0 |
| opentelemetry-api | 1.45.2 |
| packaging | 26.3 |
| pathlib-abc | 0.5.2 |
| pathspec | 1.1.1 |
| platformdirs | 4.14.7 |
| pluggy | 1.7.0 |
| prometheus-client | 0.26.0 |
| propcache | 0.5.4 |
| proto-plus | 1.29.0 |
| protobuf | 6.33.6 |
| psutil | 7.2.2 |
| psycopg | 3.3.9 |
| psycopg2-binary | 2.9.13 |
| pyasn1 | 0.6.5 |
| pyasn1-modules | 0.4.2 |
| pycparser | 3.12 |
| pydantic | 2.14.4 |
| pydantic-core | 2.50.5 |
| pydantic-settings | 2.16.3 |
| pygments | 2.21.0 |
| pyjwt | 2.15.1 |
| pyparsing | 3.3.3 |
| pyproj | 3.8.0 |
| pyreadline3 | 3.5.6 |
| pytest | 9.2.0 |
| pytest-asyncio | 1.5.0 |
| python-dateutil | 2.9.0.post0 |
| python-dotenv | 1.2.4 |
| python-multipart | 0.0.34 |
| pytz | 2026.6 |
| pywin32 | 312 |
| pyyaml | 6.0.3 |
| referencing | 0.37.0 |
| requests | 2.34.2 |
| requests-toolbelt | 1.0.0 |
| rich | 15.0.0 |
| rpds-py | 2026.9.1 |
| ruff | 0.17.6 |
| s3transfer | 0.19.3 |
| six | 1.17.0 |
| sqlalchemy | 2.1.9 |
| sse-starlette | 3.7.0 |
| starlette | 1.10.0 |
| structlog | 26.1.0 |
| tabulate | 0.10.0 |
| tenacity | 9.2.1 |
| testcontainers | 4.15.0 |
| tokenizers | 0.23.3 |
| tomli | 2.5.0 |
| tomlkit | 0.15.2 |
| toposort | 1.10 |
| tqdm | 4.70.1 |
| truststore | 0.10.5 |
| typing-extensions | 4.16.0 |
| typing-inspection | 0.4.5 |
| tzdata | 2026.6 |
| tzlocal | 5.4.5 |
| universal-pathlib | 0.3.10 |
| uritemplate | 4.2.0 |
| urllib3 | 2.8.0 |
| uvicorn | 0.54.0 |
| uvloop | 0.23.0 |
| watchdog | 6.0.0 |
| watchfiles | 1.3.0 |
| websockets | 17.4 |
| yarl | 1.25.1 |
| youtube-transcript-api | 1.2.5 |
| yt-dlp | 2026.10.26 |

| 명시적 build tool | exact |
| --- | --- |
| pip | 26.3 |
| setuptools | 84.2.1 |
| wheel | 0.48.0 |

## 프론트엔드 정책 전체 정확 버전

Common76의 자동 생성 frontend-dependencies.json versions 전체다. 실제 사용·도달 여부는 위 앱별 행렬 및 native 증거와 구분한다. 버전은 이번에 선택·검증해 동결한 값이며 출판 시점의 registry latest를 다시 조회한 결과가 아니다.

| 이름 | 정확 버전 |
| --- | --- |
| @axe-core/playwright | 4.14.0 |
| @hookform/resolvers | 7.0.5 |
| @kor-travel/toast | 0.1.3 |
| @kor-travel/tokens | 0.1.4 |
| @kor-travel/ui | 0.2.3 |
| @next/eslint-plugin-next | 16.4.6 |
| @playwright/test | 1.65.0 |
| @radix-ui/react-focus-scope | 1.3.1+kortravel.fix.2 |
| @tailwindcss/postcss | 4.3.5 |
| @tanstack/react-query | 5.107.1 |
| @tanstack/react-table | 9.3.1 |
| @tanstack/react-virtual | 3.14.26 |
| @testing-library/dom | 10.4.2 |
| @testing-library/jest-dom | 7.0.1 |
| @testing-library/react | 16.3.3 |
| @testing-library/user-event | 14.6.9 |
| @types/node | 22.20.5 |
| @types/react | 19.3.0 |
| @types/react-dom | 19.3.0 |
| @vitejs/plugin-react | 6.3.0 |
| autoprefixer | 10.6.2 |
| class-variance-authority | 0.7.1 |
| clsx | 2.1.1 |
| echarts | 6.1.0 |
| eslint | 10.14.0 |
| eslint-config-next | 16.4.6 |
| eslint-import-resolver-typescript | 4.4.5 |
| eslint-plugin-import-x | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 0.2.0 |
| eslint-plugin-react-dom | 5.30.1 |
| eslint-plugin-react-hooks | 7.1.1 |
| eslint-plugin-react-x | 5.30.1 |
| jsdom | 31.0.0 |
| lightningcss | 1.33.0+nativecss.fix.4 |
| lucide-react | 1.72.0 |
| maplibre-gl | 6.17.0 |
| motion | 14.13.0 |
| nativewind | 5.0.0-rc.1 |
| next | 16.4.6 |
| next-intl | 4.15.0 |
| openapi-typescript | 7.13.0 |
| postcss | 8.5.32 |
| pretendard | 1.3.9 |
| radix-ui | 1.8.1 |
| react | 19.3.1 |
| react-doctor | 0.9.22 |
| react-dom | 19.3.1 |
| react-hook-form | 7.92.0 |
| react-native | 0.88.1 |
| react-native-css | 3.1.0-rc.1 |
| recharts | 3.10.1 |
| shadcn | 4.23.0 |
| sharp | 0.35.5 |
| sonner | 2.0.8 |
| tailwind-merge | 3.7.0 |
| tailwindcss | 4.3.5 |
| tw-animate-css | 1.4.0 |
| typescript | 5.9.3 |
| typescript-eslint | 8.72.2 |
| undici | 8.12.4 |
| vite | 8.3.8 |
| vite-tsconfig-paths | 6.1.1 |
| vitest | 5.1.0 |
| vworld-map-core | 1.0.1 |
| vworld-map-rn | 1.0.2 |
| vworld-map-web | 1.0.4 |
| zod | 4.6.7 |
| zustand | 5.1.0 |
