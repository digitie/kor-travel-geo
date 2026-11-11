# 공통 라이브러리 비교·구현·검증 통합 보고서

작성 기준: 2026-11-11, 갱신 2026-11-11 UTC 17:22. 아래 후보 상태는 현재 작업 트리의 스냅샷이며 PR 머지·운영 배포 수용을 의미하지 않는다. 기존 9월 조사와 이후 사용자 지시를 구분한다.

## 현재 결정과 범위

사용자 후속 지시로 Geo·Map·Weather·Concierge·Docker Manager·Pinvi 웹/관리자/모바일·Transport 웹/관리자를 공통 적용 대상으로 한다. 공통으로 사용할 수 있는 라이브러리와 구현을 맞추되 앱 도메인별 의존성 목록 자체를 같게 만들지는 않는다.

| 영역 | 선택과 실제 적용 계약 | 이익 | 비용·검증 대상 |
|---|---|---|---|
| 배포 | common UI·tokens를 한 번 pack한 같은 bytes와 SHA512 원장을 사용 | 같은 버전인데 다른 구현이 설치되는 문제 방지 | 모든 앱 lock 갱신·캐시 재설치·해시 검사 필요 |
| 컴포넌트 | shadcn/ui Radix 공통 프리미티브, overlay도 같은 Radix 경로 | 접근성·포커스·스타일 수정의 공동 반영 | Base UI와 props·슬롯 차이, 회귀 시험·출처 고지 필요 |
| 표 | 공통 VirtualTable, TanStack Table9·Virtual3 | 서버 정렬·선택·비어 있음·오류·가상화 계약 공유 | v8→9 기능 등록 API 차이, 셀 remount·SSE 재연결·행 identity 검증 |
| 폼 | React Hook Form·Zod, 공통 로그인에서도 실제 등록·검증 | 수작업 입력·오류 처리 중복 감소 | 비동기 제출·SSR 기본값·hydration 전 제출 차단 검증 |
| 상태 | 인스턴스별 Zustand | 구독 범위와 상태 흐름 공유 | 비밀번호·서버 캐시를 전역 저장소에 잘못 넣지 않도록 경계 유지 |
| 글꼴·토큰 | Pretendard 로컬 파일, common 의미 토큰·Radix Tailwind bridge | 앱간 폰트·상태색·컨트롤 일관성 | 모바일 native font load·다크·앱별 테마 override 확인 |
| 웹 기반 | React/DOM19.3.1·Next16.4.6·Tailwind/postcss4.3.5 | 중복 런타임과 스타일 엔진 차이 감소 | 기존 Next14/15·React18·개별 빌드 설정 이관 비용 |
| 모바일 | NativeWind5.0.0-rc.1·react-native-css3.1.0-rc.1·Tailwind4.3.5 | 웹과 같은 Tailwind4 기준 | RC 안정성, Metro/Babel/CSS·스타일 interop·실기기/번들 검증 |
| 품질 | ESLint10.14.0·React Doctor0.9.22와 앱 CI | 설정 차이와 신규 진단 유입 차단 | 기존 진단도 실제 수정, 정당한 국소 예외만 근거 기록 |
| 지도 | maplibre-vworld-react 최신 GitHub source의 core/web/RN | 공통 지도 수정·마커 계약을 원 라이브러리로 환원 | 이동 ref 금지, package public export·CSS bundling·WebGL 검증 |


### 지도 라이브러리 적용과 원본 수정

조사 당시 원본 main은 9c46c57181d433c91f7e8837c4e4396204e9b583이며 수정 source는 9a7a348b02d61969b394c681b024d5851eef836b다. 최신 GitHub 수정본은 PR32로 main ae1e209967b3be7a3918f44e4df278add9f1376c에 머지했으며 두 commit의 전체 tree가 같다. ES6 target의 Object.entries 오류를 ES2022로 수정했고, 키 없는 로컬 geometry 지도에 명시 mapStyle을 제공하며 style 교체 시 map instance를 보존한다. core/RN은 고지·대응 소스를 동봉한1.0.1, web은1.0.3 고정 배포물을 사용한다. 기존 core1.0.0 bytes를 같은 버전으로 재발행하지 않는다.

Geo·Map·Weather·Concierge·Transport 관리자는 실제 vworld-map-web import와 core1.0.1/web1.0.3 배포물을 확인했다. Pinvi 웹·모바일도 갱신하여 실제 설치본과 lock에서 core/RN1.0.1·web1.0.3을 확인했고 세 tgz의 SHA512가 공통 정본과 같음을 검산했다. 모바일은 .native에서 RN, .web에서 웹 패키지를 지연 import하는 플랫폼 어댑터를 사용한다. fix.3 설치본에서 Android/iOS Hermes export와 웹 SSR35개 경로·375/1280폭 로그인 화면 검증을 통과했다. 최종 fix.4 채택 후에는 다시 검증한다. Docker Manager와 Transport 공개 웹은 현재 지도 기능이 없어 지도 의존성을 추가하지 않았다. 플랫폼별 core/web/RN은 같은 저장소의 서로 다른 배포 단위이며, 해당 패키지를 쓰는 앱끼리 같은 bytes를 맞춘다.

브라우저용 ESM의 CSS를 일반 Node import로 읽는 확장자 오류는 곧바로 라이브러리 결함으로 분류하지 않는다. Geo Vitest는 지도 패키지와 MapLibre를 Vite에서 inline 처리한다. 지도 source19·packed19·RN21과 정확 source의 원격 CI는 통과했다.

### 모바일 최신 스타일 엔진의 원본 수정

Expo58·RN0.88.1·NativeWind5 RC1의 실제 Android export에서 Lightning CSS1.33.0 visitor 역직렬화 오류를 재현했다. 원본 Lightning CSS와 serde-content에서 null option·Infinity·큰 정수 변환을 수정했다. fix.3을 거쳐 최종1.33.0+nativecss.fix.4에 경로 로더·고지·source/binary 검증 보완을 반영했다. GNU native와 같은 소스의 WASM을 단일 pack에 동봉하고 대응 소스·라이선스·해시를 보존한다.

원본 Rust126·배포물 Node native90/WASM90·실제 앱113개 클래스의 compiler IR8개 입력이 정상 비교본1.30.1과 같음을 확인했다. 이후 두 독립 리뷰에서 특수문자 경로의 WASM 로딩·MIT 고지·현재 소스와 binary 계보 검증·Windows fixture 문제가 확인되어 신규1.33.0+nativecss.fix.4 후보를 만들었다. 원본 Node 어댑터를 수정하여 실제 공백/#/% 경로에서 재검증했고, Rust 입력 digest가 같은 native/WASM의 재사용과 새 JS 어댑터 빌드를 구분하여 기록했다. 정확한 Lightning35fc16b의 source-gate·Ubuntu·Windows·macOS15 Intel CI가 모두 성공했다. 이전 macOS15 ARM runner 두 취소는 host 미배정이며 성공으로 바꾸지 않는다. 같은 pack의 새 Intel CI는 실제 실행했다. CI checkout 합성 merge0e92f62와 reviewed35의 tree는 같다. 두 원 리뷰어의 NativeCSS3 판정은 모두 PASS·신규0이며 Lightning PR1은 f24bb66, serde PR1은21d1c7로 머지했다. 각 merged tree와 reviewed source의 동일성을 fetch 후 확인했다. 실제 Pinvi fix.4의 최종 앱 export 결과는 별도 소비자 gate다. Babel7은 Expo58 플러그인의 peer 범위 때문에7.29.7을 사용하는 명시적 호환성 예외이며 Babel8을 통과한 것으로 표시하지 않는다.

### 차이 재발 방지

정확 버전의 정본은 common versions.json의 axes·frontendPolicy다. frontend-dependencies.json과 UI/tokens의 정책은 생성물이며 CI에서 정본과 대조한다. 직접 의존성·workspace lock 해석·중복 React 물리 설치·vendor/원장/lock의 SHA512를 검사한다. 공통 CI 코드는40자리 커밋으로 고정하고 버전·산출물 비교 데이터는 현재 common main에서 읽어 실제 관찰 SHA를 기록한다. 앱이 vendor·원장·lock을 함께 바꿔 자체 검사만 통과하는 차이도 거부한다.

Geo·Map·Weather·Concierge·Docker Manager·Pinvi 웹/모바일·Transport 웹/관리자9개 표면에 중앙 reusable CI 호출을 추가했다. foundation main에 정책 데이터가 병합된 뒤 실제 앱 CI의 성공을 확인해야 한다. native HTML Table, Base UI/Floating UI, 개별 Radix 직접 구현도 소스 검사 대상으로 한다. 최종 Lightning CSS fix.4의 exact build metadata와 bytes도 정본 축에 포함한다. 연결 workspace의 devDependencies까지 실제 CSS 빌드 그래프를 검사하고 재export·literal import()/require()·TS 외부/type 참조의 금지 private 경로 우회를 차단한다. 기준 문서의 버전 표도 versions.json에서 생성·대조한다.

## 현재 검증 상태

| 대상 | 확인한 최신 결과 | 남은 gate |
|---|---|---|
| Common |2ec5192: UI101·정책68·tokens9·실제 packed browser65·webpack/Turbopack. 정확 source의 4개 workflow·docs6개 job 모두 SUCCESS, c9 전체 SRI 일치. 원 리뷰어 B PASS/A CONDITIONAL | A-P2-10 연결 gzip 후속 header 검사 누락 수정·원 A 재확인·새 CI·PR49 머지 |
| Geo |eee413d: 단위289·lint/type·Doctor0, strict npm ci/invalid peer0, webpack/Turbopack, Chromium27+Firefox27 PASS. c9 실제 파일·lock·정본 guard 일치 | 최종 독립2리뷰·CI·PR·머지·배포 |
| Weather |d03c1dc: 단위308·lint/type/build·Doctor0·c9 정본 guard PASS. n150와 정확 HEAD frontend CI에서 browser20+tile5 PASS | PR226·독립2리뷰·중앙 main 정책 병합 후 CI·머지·배포 |
| Concierge |bcfc1b8: 단위394·lint/type/build·Doctor0, c9 strict install·정본 guard·n150 browser10/10 PASS | PR265·독립2리뷰·중앙 main 정책 병합 후 CI·머지·배포 |
| Docker Manager |4f1876b: 단위54·lint/type/build·Doctor0·c9 guard. n150 clean npm ci·production build와 desktop/mobile browser2 PASS | PR588·독립2리뷰·CI·머지·기존 systemd frontend 배포 |
| Map |aa1bd4d 문서/e3ea216 검증소스: 단위432·reporter/cleanup37·lint/type/build·Doctor0·c9 guard. D286/286·flake0·strict manifest 일치·전체 runner exit0·소유 container/network/image 잔존0 | 독립2리뷰·CI·PR·머지·Manager 정식 경로 새 frontend 이미지 배포 |
| Pinvi |f631334: Expo58/RN0.88.1·NativeWind5 RC·Tailwind4. 지도 core/web/RN 실제 파일·lock·공통 SHA512 일치. 공개 모달·AppShell Radix 이관, admin redirect/focus·RN raw text 후속 수정 | 최종 fix.4 Android/iOS/웹·강제 WASM export 및 전체 browser/unit 결과 정산·독립2리뷰·PR·CI·머지·웹 이미지 배포 |
| Transport |3c1735f: c9 실제 파일·정본 guard·금지소스10/10. 공개164/admin356 단위와 lint/type/build·Doctor0/0. native·Alpine browser 공개4/admin18 각각 PASS. backend WSL1511 PASS/39 SKIP·Docker1508 PASS/42 SKIP, 모두 exit0 | 독립2리뷰·PR·CI·머지·공개/admin 새 이미지 배포 |
| 지도 원본 |9a7a348: type/build/lint·RN21·source19/packed19·고지 pack CI·원 리뷰어2인 FIXED/신규0. PR32 mergeae1e209, main tree 동일 | 각 소비자의 최종 수용·새 배포는 별도 |
| CSS 원본 수정 |Lightning35: source/Ubuntu/Windows/macOS15 Intel CI 모두 성공. NativeCSS3 원 A/B 모두 PASS·신규0. Lightning1 mergef24bb66·serde1 merge21d1c7, reviewed tree 동일 | 소비 앱 최종 fix.4 export·독립2리뷰·배포는 별도 |

과거 실패를 보존한다. Geo의 병렬 Firefox 최초 지도 준비 시간 초과는 같은 assertion의 순차 전체27 PASS와 구분한다. Map의 이전 c6 전체 runner exit2는 Docker 제거 지연이었고 최종 c9 전체 runner exit0과 별개다. Weather 이전 server 준비 시간 초과의 최초 원인은 미확정이며 준비 확인 회귀4개와 최종20+5 PASS를 기록한다. Transport의 이전 backend 1 FAIL은 오래된 web 버전 기대값이었고 수정 후 양 환경 전체를 다시 실행했다. 환경별 SKIP 수는 PASS에 더하지 않는다. Pinvi의 이전 checkpoint unit1 FAIL·E2E6 FAIL/4 SKIP은 최신 최종 결과로 덮어 쓰지 않고 원 로그를 보존한다.

공통 source3의7e 판정은 BLOCK으로 보존한다. 이후68개 정책과 archive scanner·정확 member/rule/hash 예외를 추가했고 source4의2ec에서 A-P2-09·B-P1-08/09/10은 각 원 리뷰어가 FIXED를 확인했다. source4의 신규 A-P2-10(P2)은 두 번째 연결 gzip header의 금지 metadata를 놓치는 반례이며 현재 수정 중이다. 기존 vendor pack에 실제 비밀이 있다는 주장은 아니다. 원 A 판정은 CONDITIONAL로 유지하고 새 수정본 재확인 전 무조건 PASS로 표시하지 않는다.

[Common PR49](https://github.com/digitie/kor-travel-common/pull/49)은 초안이다. [지도 PR32](https://github.com/digitie/maplibre-vworld-react/pull/32)·[Lightning CSS fork PR1](https://github.com/digitie/lightningcss/pull/1)·[serde-content fork PR1](https://github.com/digitie/serde-content/pull/1)은 검증·독립2리뷰 후 각각 ae1e209·f24bb66·21d1c7로 일반 merge했다. 각 target branch fetch 후 reviewed source와 전체 tree 동일성을 확인했다. 라이브러리 머지3건, 앱 머지0건, 운영 신규 배포0건이다. 기존 앱 초안은 [Weather226](https://github.com/digitie/kor-travel-weather/pull/226), [Concierge265](https://github.com/digitie/kor-travel-concierge/pull/265), [Docker Manager588](https://github.com/digitie/kor-travel-docker-manager/pull/588)이다.

후보9는 한 번 생성한 같은 UI0.2.0·tokens0.1.1과 SHA512를 쓴다. 후보8→9 전체 일반 파일119개 중 checker2개만 바뀌었고 나머지 runtime/CSS/metadata117개는 byte 동일하다. VWorld3개와 fix.4도 동일하다. 따라서 checker/lock/정본 검사 갱신과 실제 제품 runtime 검증을 구분하며, 이미 출시한 같은 버전의 다른 배포물을 재발행하지 않는다.

검증용 이미지를 운영 배포로 집계하지 않는다. 각 앱의 최종 두 독립 리뷰와 CI 후 정확 merged SHA에서 새 이미지를 만들고 이미지 digest·health·로그인·대표 UI/API의 실제 결과를 기록한다. Docker Manager frontend는 기존 systemd 배포 단위를 따른다. Pinvi Expo export는 실제 기기·앱스토어 출시에 해당하지 않는다.

## 모든 직접 의존성의 기준선과 후보 비교

다음은 고정 기준선과 현재 작업 트리 package.json의 dependencies/devDependencies 전체 비교다. 선언값과 lock의 실제 설치 버전을 구분한다. 내부 workspace/SDK에는 웹 앱 필수 목록을 일괄 강제하지 않는다. 앱 도메인별로만 필요한 라이브러리는 유지한다.

<details>
<summary>Geo — eab5f7a</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @hookform/resolvers | 실행 | 5.9.2 | 7.0.5 |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.6.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @tanstack/react-table | 실행 | 8.21.3 | 9.3.1 |
| @tanstack/react-virtual | 실행 | 3.14.22 | 3.14.26 |
| @testing-library/jest-dom | 개발 | 7.0.1 | 7.0.1 |
| @testing-library/react | 개발 | 16.3.3 | 16.3.3 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| @vitejs/plugin-react | 개발 | 6.1.2 | 6.3.0 |
| class-variance-authority | 실행 | 0.7.1 | 0.7.1 |
| clsx | 실행 | 2.1.1 | 2.1.1 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-next | 개발 | 16.4.3 | 제거 |
| eslint-import-resolver-typescript | 개발 | 없음 | 4.4.5 |
| eslint-plugin-import-x | 개발 | 없음 | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-dom | 개발 | 없음 | 5.30.1 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| eslint-plugin-react-x | 개발 | 없음 | 5.30.1 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| maplibre-gl | 실행 | 6.15.0 | 6.17.0 |
| maplibre-vworld-react | 실행 | file:vendor/maplibre-vworld-react-ffa5523b5f4f.tgz | 제거 |
| next | 실행 | 16.4.3 | 16.4.6 |
| openapi-typescript | 개발 | 7.13.0 | 7.13.0 |
| postcss | 개발 | 8.5.31 | 8.5.32 |
| pretendard | 실행 | 없음 | 1.3.9 |
| radix-ui | 실행 | 1.8.1 | 1.8.1 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 7.91.0 | 7.92.0 |
| tailwind-merge | 실행 | 3.7.0 | 3.7.0 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| undici | 실행 | 8.12.3 | 8.12.4 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| vworld-map-core | 실행 | 없음 | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | 없음 | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 4.6.7 | 4.6.7 |
| zustand | 실행 | 5.0.16 | 5.1.0 |

</details>

<details>
<summary>Map admin — 32668d0</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | 1.9.0 | 제거 |
| @hookform/resolvers | 실행 | 없음 | 7.0.5 |
| @kor-travel-map/map-marker-react | 실행 | * | * |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.9.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 16.4.3 | 16.4.6 |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @tanstack/react-table | 실행 | 8.21.3 | 9.3.1 |
| @tanstack/react-virtual | 실행 | 3.14.22 | 3.14.26 |
| @testing-library/dom | 개발 | 10.4.2 | 10.4.2 |
| @testing-library/react | 개발 | 16.3.3 | 16.3.3 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| @vitejs/plugin-react | 개발 | 6.1.2 | 6.3.0 |
| class-variance-authority | 실행 | 0.7.1 | 0.7.1 |
| clsx | 실행 | 2.1.1 | 2.1.1 |
| eslint | 개발 | 10.13.0 | 10.14.0 |
| eslint-import-resolver-typescript | 개발 | 4.4.5 | 4.4.5 |
| eslint-plugin-import-x | 개발 | 4.17.1 | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 개발 | 0.2.0 | 0.2.0 |
| eslint-plugin-react-dom | 개발 | 5.28.8 | 5.30.1 |
| eslint-plugin-react-hooks | 개발 | 7.1.1 | 7.1.1 |
| eslint-plugin-react-x | 개발 | 5.28.8 | 5.30.1 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| maplibre-gl | 실행 | 6.15.0 | 6.17.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| openapi-typescript | 개발 | 7.13.0 | 7.13.0 |
| pretendard | 실행 | 1.3.9 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 0.9.1 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| sonner | 실행 | 2.0.8 | 2.0.8 |
| tailwind-merge | 실행 | 3.7.0 | 3.7.0 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| tw-animate-css | 실행 | 1.4.0 | 1.4.0 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 8.72.0 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vite-tsconfig-paths | 개발 | 6.1.1 | 6.1.1 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| vworld-map-core | 실행 | 없음 | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | 없음 | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 없음 | 4.6.7 |
| zustand | 실행 | 5.0.16 | 5.1.0 |

</details>

<details>
<summary>Map client — 32668d0</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| openapi-typescript | 개발 | 7.13.0 | 7.13.0 |
| typescript | 개발 | 5.9.3 | 5.9.3 |

</details>

<details>
<summary>Weather — b55857f</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | 1.9.0 | 제거 |
| @hookform/resolvers | 실행 | 없음 | 7.0.5 |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.9.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @radix-ui/react-dropdown-menu | 실행 | 2.2.1 | 제거 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-next | 개발 | 16.4.3 | 제거 |
| eslint-import-resolver-typescript | 개발 | 없음 | 4.4.5 |
| eslint-plugin-import-x | 개발 | 없음 | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-dom | 개발 | 없음 | 5.30.1 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| eslint-plugin-react-x | 개발 | 없음 | 5.30.1 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| maplibre-gl | 실행 | 6.15.0 | 6.17.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| postcss | 개발 | 없음 | 8.5.32 |
| pretendard | 실행 | 없음 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| vworld-map-core | 실행 | 없음 | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | 없음 | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 없음 | 4.6.7 |
| zustand | 실행 | 없음 | 5.1.0 |

</details>

<details>
<summary>Concierge — 4438328</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | ^1.8.0 | 제거 |
| @hookform/resolvers | 실행 | 5.9.1 | 7.0.5 |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.9.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @tailwindcss/postcss | 개발 | ^4.3.1 | 4.3.5 |
| @tanstack/react-query | 실행 | ^5.40.0 | 5.107.1 |
| @types/node | 개발 | ^20 | 22.20.5 |
| @types/react | 개발 | ^19.2.17 | 19.3.0 |
| @types/react-dom | 개발 | ^19.2.3 | 19.3.0 |
| autoprefixer | 개발 | ^10.4.19 | 제거 |
| class-variance-authority | 실행 | ^0.7.1 | 0.7.1 |
| clsx | 실행 | ^2.1.1 | 2.1.1 |
| eslint | 개발 | ^9.39.4 | 10.14.0 |
| eslint-config-next | 개발 | ^16.2.7 | 제거 |
| eslint-import-resolver-typescript | 개발 | 없음 | 4.4.5 |
| eslint-plugin-import-x | 개발 | 없음 | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | ^1.17.0 | 1.72.0 |
| maplibre-gl | 실행 | ^6.0.0 | 6.17.0 |
| next | 실행 | ^16.2.7 | 16.4.6 |
| postcss | 개발 | ^8.4.38 | 8.5.32 |
| pretendard | 실행 | 1.3.9 | 1.3.9 |
| react | 실행 | ^19.2.8 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | ^19.2.8 | 19.3.1 |
| react-hook-form | 실행 | ^7.51.5 | 7.92.0 |
| shadcn | 실행 | ^4.10.0 | 제거 |
| tailwind-merge | 실행 | ^3.6.0 | 3.7.0 |
| tailwindcss | 개발 | ^4.3.1 | 4.3.5 |
| tw-animate-css | 개발 | ^1.4.0 | 1.4.0 |
| typescript | 개발 | ^5.4.5 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vitest | 개발 | ^4.1.9 | 5.1.0 |
| vworld-map-core | 실행 | file:vendor/vworld-map-core-1.0.0.tgz | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | file:vendor/vworld-map-web-1.0.0.tgz | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | ^4.4.3 | 4.6.7 |
| zustand | 실행 | 없음 | 5.1.0 |

</details>

<details>
<summary>Docker Manager — 351e15b</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @kor-travel/tokens | 실행 | 없음 | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | 없음 | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @playwright/test | 개발 | 없음 | 1.65.0 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @testing-library/dom | 개발 | 10.4.2 | 10.4.2 |
| @testing-library/jest-dom | 개발 | 7.0.1 | 7.0.1 |
| @testing-library/react | 개발 | 16.3.3 | 16.3.3 |
| @testing-library/user-event | 개발 | 14.6.8 | 14.6.9 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| @vitejs/plugin-react | 개발 | 6.1.2 | 6.3.0 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-next | 개발 | 16.4.3 | 제거 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-dom | 개발 | 없음 | 5.30.1 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| eslint-plugin-react-x | 개발 | 없음 | 5.30.1 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| postcss | 개발 | 8.5.31 | 8.5.32 |
| pretendard | 실행 | 없음 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| recharts | 실행 | 3.10.1 | 3.10.1 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| zod | 실행 | 없음 | 4.6.7 |
| zustand | 실행 | 없음 | 5.1.0 |

</details>

<details>
<summary>Pinvi web/admin — d42ac95</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @axe-core/playwright | 개발 | 4.14.0 | 4.14.0 |
| @base-ui/react | 실행 | 1.9.0 | 제거 |
| @eslint-react/eslint-plugin | 개발 | 없음 | 5.30.1 |
| @hookform/resolvers | 실행 | 5.9.2 | 7.0.5 |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.9.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @pinvi/api-client | 실행 | * | * |
| @pinvi/design-tokens | 실행 | * | * |
| @pinvi/domain | 실행 | * | * |
| @pinvi/hooks | 실행 | * | * |
| @pinvi/i18n | 실행 | * | * |
| @pinvi/schemas | 실행 | * | * |
| @pinvi/state | 실행 | * | * |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @tanstack/react-table | 실행 | 8.21.3 | 9.3.1 |
| @tanstack/react-virtual | 실행 | 3.14.22 | 3.14.26 |
| @testing-library/jest-dom | 개발 | 7.0.1 | 7.0.1 |
| @testing-library/react | 개발 | 16.3.3 | 16.3.3 |
| @testing-library/user-event | 개발 | 14.6.8 | 14.6.9 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.2.18 | 19.3.0 |
| @types/react-dom | 개발 | 19.2.7 | 19.3.0 |
| class-variance-authority | 실행 | 0.7.1 | 0.7.1 |
| clsx | 실행 | 2.1.1 | 2.1.1 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-next | 개발 | 16.4.3 | 제거 |
| eslint-plugin-import-x | 개발 | 없음 | 4.18.1 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| globals | 개발 | 없음 | 17.14.0 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| maplibre-gl | 실행 | 6.15.0 | 6.17.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| next-intl | 실행 | 4.14.9 | 4.15.0 |
| postcss | 개발 | 8.5.31 | 8.5.32 |
| pretendard | 실행 | 1.3.9 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 7.91.0 | 7.92.0 |
| tailwind-merge | 실행 | 3.7.0 | 3.7.0 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| vworld-map-core | 실행 | file:../mobile/vendor/vworld-map-core-1.0.0.tgz | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | file:vendor/vworld-map-web-1.0.2.tgz | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 4.6.7 | 4.6.7 |
| zustand | 실행 | 5.0.16 | 5.1.0 |

</details>

<details>
<summary>Pinvi mobile — d42ac95</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @babel/core | 개발 | 7.29.7 | 7.29.7 |
| @kor-travel/tokens | 실행 | 없음 | file:../web/vendor/kor-travel-tokens-0.1.1.tgz |
| @maplibre/maplibre-react-native | 실행 | 11.5.0 | 11.5.1 |
| @pinvi/api-client | 실행 | * | * |
| @pinvi/design-tokens | 실행 | * | * |
| @pinvi/domain | 실행 | * | * |
| @pinvi/hooks | 실행 | * | * |
| @pinvi/i18n | 실행 | * | * |
| @pinvi/schemas | 실행 | * | * |
| @pinvi/state | 실행 | * | * |
| @react-native-async-storage/async-storage | 실행 | 2.2.0 | 3.1.1 |
| @tailwindcss/postcss | 개발 | 없음 | 4.3.5 |
| @tanstack/react-query | 실행 | 5.104.5 | 5.107.1 |
| @types/react | 개발 | 19.2.18 | 19.3.0 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-expo | 개발 | 57.0.2 | 제거 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| expo | 실행 | 57.0.32 | 58.0.23 |
| expo-build-properties | 실행 | 57.0.23 | 58.0.12 |
| expo-constants | 실행 | 57.0.23 | 58.0.15 |
| expo-dev-client | 실행 | 57.0.21 | 58.0.19 |
| expo-font | 실행 | 없음 | 58.0.12 |
| expo-linking | 실행 | 57.0.13 | 58.0.16 |
| expo-location | 실행 | 57.0.23 | 58.0.21 |
| expo-router | 실행 | 57.0.30 | 58.0.30 |
| expo-secure-store | 실행 | 57.0.4 | 58.0.3 |
| expo-status-bar | 실행 | 57.0.1 | 58.0.5 |
| expo-web-browser | 실행 | 57.0.3 | 58.0.8 |
| lightningcss | 개발 | 없음 | file:../web/vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| nativewind | 실행 | 4.2.7 | 5.0.0-rc.1 |
| postcss | 개발 | 없음 | 8.5.32 |
| pretendard | 실행 | 없음 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| react-native | 실행 | 0.86.3 | 0.88.1 |
| react-native-css | 실행 | 없음 | 3.1.0-rc.1 |
| react-native-reanimated | 실행 | 4.7.1 | 4.7.1 |
| react-native-safe-area-context | 실행 | 5.7.0 | 5.11.1 |
| react-native-screens | 실행 | 4.26.2 | 4.30.1 |
| react-native-web | 실행 | 0.21.4 | 0.21.4 |
| react-native-worklets | 실행 | 0.13.0 | 0.13.1 |
| tailwindcss | 개발 | 3.4.19 | 4.3.5 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vworld-map-core | 실행 | file:vendor/vworld-map-core-1.0.0.tgz | file:../web/vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-rn | 실행 | file:vendor/vworld-map-rn-1.0.0.tgz | file:../web/vendor/vworld-map-rn-1.0.1.tgz |
| vworld-map-web | 실행 | 없음 | file:../web/vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 4.6.7 | 4.6.7 |
| zustand | 실행 | 5.0.16 | 5.1.0 |

</details>

<details>
<summary>Transport web — 59e1d82</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | 1.9.0 | 제거 |
| @kor-travel/tokens | 실행 | 없음 | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | 없음 | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @tailwindcss/postcss | 실행 | 4.3.3 | 4.3.5 |
| @testing-library/jest-dom | 개발 | 7.0.1 | 7.0.1 |
| @testing-library/react | 개발 | 16.3.3 | 16.3.3 |
| @testing-library/user-event | 개발 | 14.6.8 | 14.6.9 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| class-variance-authority | 실행 | 0.7.1 | 0.7.1 |
| cn | 실행 | 0.5.0 | 제거 |
| date-fns | 실행 | 4.4.0 | 4.4.0 |
| eslint | 개발 | 없음 | 10.14.0 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| postcss | 실행 | 8.5.31 | 8.5.32 |
| pretendard | 실행 | 없음 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-day-picker | 실행 | 10.0.2 | 10.0.2 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| shadcn | 실행 | 4.22.1 | 제거 |
| tailwindcss | 실행 | 4.3.3 | 4.3.5 |
| tw-animate-css | 실행 | 1.4.0 | 1.4.0 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| zod | 실행 | 없음 | 4.6.7 |
| zustand | 실행 | 없음 | 5.1.0 |

</details>

<details>
<summary>Transport admin — 59e1d82</summary>

| 라이브러리 | 종류 | 기준선 선언 | 후보 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | 1.9.0 | 제거 |
| @kor-travel/parking-ui | 실행 | file:../../../frontend/src | file:../../../frontend/src |
| @kor-travel/tokens | 실행 | file:vendor/kor-travel-tokens-0.1.0.tgz | file:vendor/kor-travel-tokens-0.1.1.tgz |
| @kor-travel/ui | 실행 | file:vendor/kor-travel-ui-0.1.0-dev.9.tgz | file:vendor/kor-travel-ui-0.2.0.tgz |
| @next/eslint-plugin-next | 개발 | 없음 | 16.4.6 |
| @playwright/test | 개발 | 1.64.1 | 1.65.0 |
| @tailwindcss/postcss | 개발 | 4.3.3 | 4.3.5 |
| @types/node | 개발 | 22.20.5 | 22.20.5 |
| @types/react | 개발 | 19.3.0 | 19.3.0 |
| @types/react-dom | 개발 | 19.3.0 | 19.3.0 |
| @types/supercluster | 개발 | 7.1.3 | 7.1.3 |
| class-variance-authority | 실행 | 0.7.1 | 0.7.1 |
| clsx | 실행 | 2.1.1 | 2.1.1 |
| echarts | 실행 | 6.1.0 | 6.1.0 |
| eslint | 개발 | 9.39.5 | 10.14.0 |
| eslint-config-next | 개발 | 16.4.3 | 제거 |
| eslint-plugin-jsx-a11y-x | 개발 | 없음 | 0.2.0 |
| eslint-plugin-react-hooks | 개발 | 없음 | 7.1.1 |
| jsdom | 개발 | 30.1.3 | 31.0.0 |
| lightningcss | 개발 | 없음 | file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz |
| lucide-react | 실행 | 1.61.0 | 1.72.0 |
| maplibre-gl | 실행 | 6.15.0 | 6.17.0 |
| next | 실행 | 16.4.3 | 16.4.6 |
| pretendard | 실행 | 없음 | 1.3.9 |
| react | 실행 | 19.3.1 | 19.3.1 |
| react-doctor | 개발 | 없음 | 0.9.22 |
| react-dom | 실행 | 19.3.1 | 19.3.1 |
| react-hook-form | 실행 | 없음 | 7.92.0 |
| tailwind-merge | 실행 | 3.7.0 | 3.7.0 |
| tailwindcss | 개발 | 4.3.3 | 4.3.5 |
| tw-animate-css | 개발 | 1.4.0 | 1.4.0 |
| typescript | 개발 | 5.9.3 | 5.9.3 |
| typescript-eslint | 개발 | 없음 | 8.72.2 |
| vite | 개발 | 8.3.5 | 8.3.8 |
| vitest | 개발 | 5.0.5 | 5.1.0 |
| vworld-map-core | 실행 | file:vendor/vworld-map-core-1.0.0.tgz | file:vendor/vworld-map-core-1.0.1.tgz |
| vworld-map-web | 실행 | file:vendor/vworld-map-web-1.0.1.tgz | file:vendor/vworld-map-web-1.0.3.tgz |
| zod | 실행 | 없음 | 4.6.7 |
| zustand | 실행 | 없음 | 5.1.0 |

</details>

## 이전 조사 기록

다음 내용은 최초 도입 타당성 조사의 역사 기록이다. React18·Base UI·모바일 제외·단계적 표 이관 등 당시 권고와 버전 표는 위 2026-11-11 사용자 결정으로 대체되었다.

## kor-travel-common 공통 라이브러리 도입 검토 보고서

- 작성일: 2026-09-05
- 상태: **도입 검토와 단계별 권고안**. 이 문서의 머지는 라이브러리 구현·패키지 발행·서비스 이관 완료를 뜻하지 않는다.
- 대상: `kor-travel-geo`, `kor-travel-map`, `kor-travel-weather`, `kor-travel-concierge`, `kor-travel-docker-manager`, Pinvi의 웹 admin.
- 조사 방법: 각 저장소의 원격 `main`을 fetch한 뒤 커밋된 소스를 비교했다. 커밋 기준과 재현 가능한 파일 링크는 §12에 둔다. 로컬 미커밋 코드·운영 배포 버전은 근거에서 제외했다.

### 1. 결론과 권고

**도입을 권고한다. 다만 `kor-travel-common`은 작게 시작하는 공통 UI 저장소로 두고, 모든 서비스의 공통 코드를 한 패키지로 모으는 방식은 피한다.** 현재 가장 확실한 이익은 admin UI를 여러 저장소로 복사하고 재동기화하는 비용을 줄이는 데 있다. 백엔드·인증까지 함께 통합할 근거는 부족하다.

권고안은 다음과 같다.

1. 저장소 이름은 요청한 `kor-travel-common`으로 한다. 첫 배포 단위는 **디자인 토큰과 React admin UI**로 한정한다. 실제로 필요한 두 패키지만 만들고, 비어 있는 `core`·`utils`·`auth`·`python` 패키지를 미리 만들지 않는다.
2. **map admin과 Pinvi admin을 첫 공동 소비자**로 삼는다. 이식 관계가 소스에 명시되어 있어 공통화 후보가 가장 뚜렷하다. geo는 초기에 계약 검증에 참여하되 React 18·Radix 차이를 해결한 후 소비를 확대한다.
3. 간격·컨트롤 크기·상태 표현·작은 폼 부품부터 옮긴다. `DataTable`은 이익이 크지만 공개 계약도 커서 후속 단계에서 다룬다.
4. 브랜드 색상, 메뉴와 라우트, 데이터 조회, 인증·권한, 서비스별 작업 실행은 각 앱이 소유한다. Pinvi 사용자 웹과 모바일은 첫 이관 대상에서 제외한다.
5. 두 소비자에서 실제 설치·빌드·동작 검증을 통과한 버전을 고정해 각각 배포한다. 공통 라이브러리 릴리스가 모든 앱의 동시 배포를 요구하게 만들지 않는다.

**착수 전 핵심 조건은 코드 출처·라이선스 확인, 두 앱에서 같은 의미를 갖는 API 확정, React/스타일 배포 검증이다.** 이 조건을 충족하지 못하면 당장 코드를 옮기기보다 공유할 규약과 회귀 사례를 먼저 정리하는 편이 낫다.

### 2. 현재 기술 구성과 공유 가능성

아래 버전은 조사 커밋의 `package.json`에 적힌 **요구 범위**다. lockfile이 선택한 설치 버전이나 현재 운영 버전, 공식 지원·보안 적합성을 의미하지 않는다. 각 행의 패키지 근거는 §12의 [G1]~[P1]이다.

| 소비자 | Next.js / React 요구 범위 | 스타일·UI 기반 | 도입 시 의미 |
|---|---|---|---|
| geo admin | `^16.2.12` / `^18.3.1` | Tailwind `^4.0.0`, `radix-ui`, TanStack Table/Virtual | React 18 ref·Radix `asChild` 계약 보존 필요 |
| map admin | `16.2.12` / `^19.2.6` | Tailwind `^4.3.0`, Base UI, TanStack Table/Virtual | 최근 admin 표현 규약의 주요 원본 후보 |
| weather admin | `^15.2.0` / `^19.0.0` | 자체 `tokens.css`·CSS, Tailwind 직접 의존성 없음 | CSS 토큰은 도입하기 쉽지만 Tailwind 소스 패키지는 설치만으로 적용되지 않음 |
| concierge 관리 UI | `^16.2.7` / `^19.2.8` | Tailwind `^4.3.1`, Base UI, React Hook Form | 작은 UI 부품 후보, map 전체 구현과 동일하다고 볼 근거는 없음 |
| docker-manager admin | `^14.1.4` / `^18.2.0` | Tailwind `^4.0.0`, 자체 컴포넌트, Recharts | Next/React 세대 차이와 운영 작업 UI 특성 고려 필요 |
| Pinvi 웹 admin | `16.3.3` / `^19.0.0` | Tailwind `^4.3.3`, Base UI 일부 사용, TanStack Table/Virtual | map 이식 코드 존재. 사용자 웹·모바일 토큰과 충돌 방지 필요 |

모두 React를 사용한다는 사실만으로 바로 같은 라이브러리를 소비할 수는 없다. 특히 geo와 docker-manager의 React 18, map·Pinvi의 서로 다른 버튼 구현, weather의 CSS 구성이 초기 호환 비용을 만든다. 기존 프레임워크 업그레이드와 공통화는 독립 작업으로 계획해야 실패 원인을 구분할 수 있다.

Python 백엔드는 별도 실행·배포 표면이다. npm React 패키지로 Python 함수를 공유할 수 없으며, 언어별 구현을 같은 저장소에 넣어도 테스트·의존성·버전 관리는 각각 필요하다. 이번 조사에서는 Python 전체 함수의 중복률을 측정하지 않았으므로 백엔드 공통 패키지의 경제성을 입증한 것으로 해석하면 안 된다.

### 3. 실제 중복과 차이: 추측이 아닌 도입 근거

#### 3.1 map → Pinvi 이식은 이미 발생했다

Pinvi `components/admin/ui/data-table.tsx`는 map의 `data-table.tsx`를 이식했다고 명시한다. import 경로와 색 토큰을 Pinvi에 맞췄고, `headerStyle` 같은 추가 차이도 기록한다. 조사 시점 파일 길이는 map 799줄, Pinvi 853줄이다. 이 길이는 주석·공백을 포함하며 절감 가능한 코드량이 아니다. [M2], [P2]

두 UI 디렉터리의 바로 아래 `.ts`·`.tsx` 파일에서 `.test.` 파일을 제외하면 map 30개, Pinvi 28개이고, **파일명이 같은 것은 27개지만 바이트 단위로 동일한 파일은 0개**였다. 이는 “그대로 옮기면 되는 중복 27개”라는 뜻이 아니다. 공통 조상·유사한 표면 위에 경로, 스타일, 실제 동작의 차이가 쌓였다는 근거다.

재현 기준은 [M2]·[P2]의 상위 `ui` 디렉터리에서 위 조건의 파일명 집합을 비교하고, 교집합 파일의 내용을 바이트 단위로 비교하는 것이다. 프로젝트 전체 중복률, 의미상 동일 함수 비율, 테스트 커버리지는 측정하지 않았다.

#### 3.2 geo는 반복 동기화 비용을 이미 부담했다

geo의 재개 문서에는 T-302의 map workbench 동기화와 T-303의 콘텐츠 표현 동기화가 연속해서 기록되어 있다. 공통 UI 수정이 소비 앱의 버전 갱신으로 전달되면 이런 반복 이식 비용을 줄일 가능성이 크다. 다만 테마 연결과 소비 앱 검증 비용까지 사라지는 것은 아니다. [G2]

#### 3.3 같은 이름의 버튼도 계약이 다르다

| 구현 | 관찰한 차이 | 무리하게 통합했을 때의 회귀 |
|---|---|---|
| geo `Button` | Radix `Slot`, `asChild`, React 18 `forwardRef` | 대화상자 트리거의 ref·포커스 복귀, 링크 합성 손상 |
| map `Button` | Base UI 기반, 진행 중 활성화 차단·포커스 유지 | `loading` 중 중복 실행, 키보드 동작 변화 |
| Pinvi admin `Button` | map에서 이식했지만 native `button`·`forwardRef`, 기본 `type="button"`, `render`/`asChild` 미제공 | 기본 submit으로 바뀌면 의도치 않은 폼 제출 |

근거: [G3], [M3], [P3]. 따라서 초기에 모든 primitive 엔진을 선택 가능하게 하는 거대한 호환 계층을 만들기보다, 합의할 수 있는 최소 동작부터 정하고 기존 호출부를 명시적으로 이관해야 한다. 엔진 의존성이 큰 overlay는 뒤로 미룬다.

#### 3.4 테이블은 데이터 책임이 다르다

geo `VirtualTable`은 `VirtualColumn` 계약과 클라이언트 검색·정렬을 갖고 기본 `as="grid"`이며, 의미 구조를 가진 `as="table"` 모드도 제공한다. map과 Pinvi의 `DataTable`은 TanStack `ColumnDef`를 받고 서버 정렬을 뜻하는 `manualSorting=true`를 기본으로 한다. [G4], [M2], [P2]

이름만 통일하면 서버가 페이지별로 보내는 데이터를 브라우저에서 부분 정렬해 전체 순서처럼 보이게 만들 수 있다. 공통화 이후에도 조회·필터·페이지네이션의 소유자는 앱이어야 한다. 전체 데이터를 가진 목록의 클라이언트 정렬과 서버 목록의 제어형 정렬을 명시적으로 구분하고, 행 ID·선택 상태·접근성·가상화 조건을 먼저 검증해야 한다.

#### 3.5 토큰을 공유해도 제품의 정체성은 남겨야 한다

weather `tokens.css`에는 map에서 가져온 크기·팔레트 관련 기록이 있다. Pinvi는 이미 `@pinvi/design-tokens`를 두고, 웹 `globals.css`가 웹·모바일 토큰 정본과 admin 예외를 설명한다. [W2], [P4], [P5]

공유할 것은 `surface`, `text`, `border`, `danger`, `focus` 같은 **의미와 크기 규약**이다. 실제 브랜드 값과 사용자 UI의 타이포·터치 밀도는 앱이 결정한다. `@pinvi/design-tokens`를 새 라이브러리로 통째로 옮기거나 같은 값을 두 저장소에서 따로 수정하게 만들면 기존 공유 구조를 오히려 약화시킨다.

#### 3.6 인증은 유사한 화면 아래 다른 경계를 가진다

geo는 Next.js에서 세션을 검증하고 백엔드에는 신뢰된 프록시 신원을 전달한다. geo `auth.ts`에는 프로세스 메모리 기반 세션 폐기 상태가 있으며, docker-manager의 Python 인증 라우터는 자체 세션 생성·폐기 함수를 호출한다. geo의 최근 작업 일지도 로그인 일치화 검토가 기존 아키텍처와 충돌해 취소된 경위를 기록한다. [G5], [G6], [G7], [D2]

공통 로그인 폼을 쓸 수 있는 것과 세션 저장·역할 판정·쿠키·CSRF 정책을 통합할 수 있는 것은 다른 결정이다. `kor-travel-common`에 인증 서비스를 숨겨 넣거나 공통 세션 secret을 요구해서는 안 된다.

### 4. 장점과 그것이 성립하는 조건

| 장점 | 이 프로젝트들에서 기대하는 효과 | 성립 조건·남는 비용 |
|---|---|---|
| 중복 수정 감소 | map의 테이블·상태 UI 수정 내용을 Pinvi·geo로 반복 이식하는 횟수 감소 | 소비 앱이 실제로 패키지를 갱신해야 함. 수정 한 번으로 운영 전체가 자동 갱신되지는 않음 |
| 접근성 수정 재사용 | 포커스 복귀·진행 상태·폼 설명 연결을 공통 회귀 사례로 관리 | 테마별 대비와 실제 화면의 키보드 흐름은 앱에서도 검증 |
| 운영 UX 일관성 | 빈 상태·오류·재시도·정렬·확인 동작의 학습 비용 감소 | 업무별 위험도와 설명 문구는 앱이 소유 |
| 신규 admin 개발 속도 | 검증된 폼·패널·목록 표현을 조립 | 초기 API 설계와 문서·예제 비용을 선투자 |
| 변경 추적과 재현성 | 어느 앱이 어떤 UI 버전을 쓰는지 명시 | 릴리스 기록·lockfile·소비자 버전 목록 유지 |
| 테스트 자산 집중 | 같은 부품의 세부 동작 회귀를 한곳에서 검증 | 라이브러리 테스트만으로 앱 통합·인증·배포 검증을 대체하지 않음 |
| 제품 간 시각 차이 관리 | 구조는 같게, 브랜드는 각자 유지 | 의미 토큰과 테마 경계를 지켜야 함 |

### 5. 단점·실패 가능성과 완화책

| 단점·위험 | 구체적인 실패 모습 | 완화책 |
|---|---|---|
| 공통 변경의 영향 확대 | 버튼 기본 동작 하나가 여러 admin의 폼을 깨뜨림 | 두 대표 소비자 검증 → 한 앱 선행 배포 → 나머지 갱신 |
| 릴리스 조정 비용 | 간단한 앱 수정도 common PR·릴리스·앱 PR이 필요 | 앱 전용 수정은 앱에 유지. 공통 의미가 확인된 수정만 승격 |
| 추상화 비대화 | `isGeo`, `isPinvi` 분기와 수십 개 예외 옵션 | 제품명 분기 금지. 두 소비자가 동일 의미로 쓰지 못하면 추출 보류 |
| 버전 분산 | 앱마다 오래된 common을 고정해 동기화 비용 재발 | 지원 버전·갱신 담당자·폐기 일정을 기록 |
| 프레임워크·primitive 차이 | React 중복, ref 손실, 서버 코드의 브라우저 유입 | React를 peer로 두고 지원 조합 실검증, client/server 진입점 분리 |
| CSS 누수·스타일 누락 | Pinvi 사용자 페이지가 바뀌거나 설치한 버튼이 무스타일로 표시 | admin 범위 CSS, 토큰 접두사, 배포 산출물의 CSS 포함·실제 적용 검사 |
| 도메인 결합 | 테이블이 Geo API를 호출하거나 메뉴가 Map URL을 앎 | 데이터·행동·링크를 앱이 전달. 공통 UI는 도메인 API import 금지 |
| 번들·의존성 증가 | 작은 버튼 소비에 지도·차트·전체 테이블 의존성이 따라옴 | 필요한 공개 진입점만 사용하고 무거운 기능은 실제 필요 시 별도 배포 단위 검토 |
| 배포 공급망 증가 | registry 권한 만료로 앱 빌드 실패 | CI 설치 경로 검증, 배포 권한 최소화, 버전·산출물 보존 |
| 담당자 병목 | 모든 앱의 UI 수정 요청이 한 저장소에 대기 | 공통 코드 담당과 소비 앱 담당을 명시. 긴급 패치 경로 마련 |
| 라이선스 불일치 | 다른 조건의 코드를 새 패키지로 복사하고 임의로 MIT 표기 | 파일 출처·권리·고지 검토 후 배포 정책 확정(§9) |

**가장 큰 비용은 파일 이동 자체보다 차이의 의미를 판정하는 작업이다.** 현재의 코드 복제가 나쁜 추상화보다 항상 비싼 것은 아니다. 변경 속도·의미가 다른 기능은 중복을 일시 허용하는 것이 더 싸다.

### 6. 구조 대안 비교

| 대안 | 이점 | 비용·한계 | 판단 |
|---|---|---|---|
| 현재처럼 소스 복사·수동 동기화 | 앱별 수정과 배포가 쉬움 | 이식 누락·동작 차이 누적, 회귀 수정 반복 | 도메인별 차이가 큰 영역에는 계속 유효 |
| 소스 배포용 registry·템플릿 | 시작 코드·표현 규약을 전달하고 앱이 소유 | 이후 수정은 자동 전파되지 않음 | 변경이 잦고 앱별 변형이 큰 레이아웃에 적합 |
| 거대한 단일 common 패키지 | 설치·버전 하나 | JS/Python 혼재, 사용하지 않는 의존성, 광범위한 릴리스 결합 | 비권고 |
| **독립 common 저장소 + 작은 버전 패키지** | 앱 저장소·배포 독립성과 실질적 코드 재사용을 함께 유지 | 패키징·배포·소비자 검증 비용 | **권고** |
| 모든 서비스를 한 모노레포로 이동 | 공통 변경과 소비자 수정을 하나의 커밋으로 검증 가능 | 권한·CI·기존 운영 체계까지 큰 변경 | 이 요청을 해결하기 위한 선행 조건으로는 과도함 |
| microfrontend·원격 런타임 UI | 중앙 UI를 실행 중 교체 가능 | 가용성·버전·보안·스타일 충돌의 런타임 비용 | 현재의 코드 공유 문제에는 부적합 |

common 저장소 내부를 작은 workspace로 구성하는 것과 모든 서비스를 같은 모노레포로 합치는 것은 별개다. 첫 단계는 전자만 필요하다. 앱과 common을 `file:../...`로 묶거나 Git submodule을 운영 배포 경로로 쓰면 개발 머신에서는 되지만 독립 CI에서 재현되지 않는 결합이 생기기 쉽다.

### 7. 권고 패키지와 책임 경계

#### 7.1 이름과 최소 구성

저장소 이름은 `kor-travel-common`으로 유지한다. npm 이름은 registry와 소유 scope를 확인한 후 확정한다. GitHub Packages를 쓴다면 계정 또는 조직 scope가 필요하므로 `@digitie/kor-travel-common-tokens`, `@digitie/kor-travel-common-ui` 같은 형식이 후보가 된다. 이 이름의 사용 가능성이나 발행 권한을 이번 보고서에서 확인한 것은 아니다. [E5]

| 배포 단위 | 포함할 것 | 포함하지 않을 것 |
|---|---|---|
| 토큰 패키지 | 의미 토큰 계약, 간격·크기 기준, CSS 변수와 필요한 타입 | 전역 reset, 폰트 강제 로딩, Pinvi 모바일 팔레트 복제 |
| React UI 패키지 | 실제 두 소비자가 쓰는 작은 표시·입력 부품, 후속 검증된 목록 UI | Next.js 라우터·쿠키, 환경변수 직접 읽기, API 호출, DB, 지도 엔진 |

초기에는 작은 내부 helper를 UI 패키지 안에 둔다. React 없이 독립적으로 소비하는 순수 TypeScript 기능이 두 곳 이상에서 확인될 때 별도 패키지를 검토한다. Python 공유는 그 뒤 별도 수요 조사와 배포 설계를 거친다.

의존 관계는 **앱 → 공통 UI → 토큰**이다. 앱의 도메인 모듈을 common이 import해서는 안 된다. UI는 `rows`, `loading`, 오류 설명, 이벤트 callback을 받고, 앱은 실제 REST 호출·권한 판정·캐시 무효화를 수행한다.

#### 7.2 기능별 이동 판단

| 영역 | 권고 | 이유·조건 |
|---|---|---|
| 간격·컨트롤 크기·의미 토큰 | 우선 공유 | 반복 이식 근거가 있고 의존성이 작음. 브랜드 값은 앱 매핑 |
| Badge·빈 상태·오류 표시·폼 설명 | 우선 후보 | 상태 의미·접근성·문구 주입 계약을 먼저 일치시킴 |
| Button·Input | 작은 시범 범위 | submit 기본값, ref, loading·disabled 의미 합의 필요 |
| Dialog·Popover·Tooltip | 후속 | portal·포커스·primitive 엔진 차이를 실제 호출부에서 검증 |
| DataTable | 후속 우선순위 높음 | 이식 근거는 강하나 서버 정렬·선택·가상화 계약과 의존성 큼 |
| AppShell·사이드바·내비게이션 | 구조 일부만 후보 | 앱별 URL·메뉴·권한·제품명은 앱에 유지 |
| 날짜·수량·오류 문구 helper | 의미가 일치하는 것만 | 타임존·단위·반올림·null 처리 차이를 단순 중복으로 보지 않음 |
| React Query hook·API 클라이언트 | 기본적으로 앱에 유지 | query key·인증·재시도·취소·도메인 오류 정책이 다름 |
| Geo DTO·주소 처리·공간 쿼리 | Geo 소유 유지 | 공개 `AsyncAddressClient`·DTO 정본과 기존 계층 유지 |
| MapLibre/VWorld 기능 | 기존 전용 라이브러리 유지 | geo의 `maplibre-vworld-react` 등 기존 제공 경계와 중복 방지 |
| 로그인·세션·권한·CSRF | 첫 범위에서 제외 | 공유 UI와 신뢰 경계 통합을 분리해야 함 |
| Dagster 작업·백업/복원·컨테이너 제어 | 앱에 유지 | 작업 수명·재시도·취소·데이터 보호의 도메인 차이 |
| CI·lint·TypeScript 설정 | 별도 필요 검토 | 프레임워크 버전을 숨기거나 모든 앱 빌드를 묶는 공통 설정 금지 |

외부 제공자 API를 단순 전달하는 facade는 추가하지 않는다. 이미 공개된 클라이언트·타입 모델을 직접 소비하고, 공통 라이브러리를 서비스 간 간접 호출 계층으로 만들지 않는다. geo의 프론트엔드 DB 접근 금지와 백엔드 의존 방향도 그대로 유지한다.

#### 7.3 스타일과 React 배포 계약

첫 시범에서는 **범위를 제한한 사전 빌드 CSS + CSS 변수**를 우선 검토한다. weather처럼 Tailwind가 직접 없는 앱에도 적용 가능하고, 소비 앱의 클래스 탐지 설정에 덜 의존하기 때문이다. 대신 CSS 생성·크기·테마 검증을 common 릴리스가 책임져야 한다. 처음부터 두 스타일 배포 방식을 동시에 지원하지 않는다.

Tailwind 소스 배포를 고르면 외부 패키지는 자동 탐지 대상에서 빠질 수 있으므로 소비 앱에 `@source` 등 명시적 등록이 필요하다. 동적으로 이어 붙인 클래스는 별도로 주의해야 한다. v3 방식의 Pinvi 토큰 정본도 함께 검증한다. [E1]

구현 시 확인할 계약은 다음과 같다.

- CSS 변수와 클래스에는 공통 접두사를 쓰고 admin 경계 안에 적용한다. 전역 `button`, `table`, `:root` 재정의로 사용자 UI에 영향을 주지 않는다. overlay portal이 admin DOM 밖에 렌더될 때도 같은 테마 범위를 받도록 검증한다.
- React·React DOM은 앱이 제공하는 peer 의존성으로 두고 번들에 중복 포함하지 않는다. React 18/19 동시 지원은 테스트한 뒤 선언한다. 지원이 어렵다면 호환되는 앱만 먼저 채택한다. [E2]
- 이벤트·hook이 필요한 진입점에는 `'use client'`를 보존한다. 서버 데이터·secret·Node 전용 모듈이 브라우저 진입점으로 섞이지 않게 한다. [E3]
- 배포 기본안은 ESM·타입 선언·CSS 산출물이다. CommonJS 추가 지원은 실제 소비자가 필요할 때 결정한다. `exports`로 공개 경계를 지정하고 내부 파일 deep import를 지원하지 않는다. [E4]
- 소스 TypeScript를 배포하는 대안은 Next.js `transpilePackages` 설정을 포함한 소비자 빌드 검증이 필요하다. 개발 workspace 링크만 성공한 상태를 패키지 검증 완료로 보지 않는다. [E6]
- CSS가 제거되지 않도록 배포 파일 목록과 부작용 표기를 검토하고, `npm pack` 산출물을 설치해 사용하지 않는 대형 모듈 유입·누락된 CSS·타입을 확인한다.

### 8. 버전·릴리스·운영 방식

초기 두 패키지는 한 릴리스 묶음으로 관리하되 앱마다 채택 시점을 정한다. 공통 저장소에 기본 검증용 앱을 두고, 실제 map·Pinvi 소비 PR에서 다시 검증한다. 전체 여섯 앱을 매번 전부 배포하는 방식은 피한다.

1. 공통 PR에 소비자 목록, 동작 변화, 테마 영향, 마이그레이션 방법을 적는다.
2. 라이브러리 자체 테스트와 배포 tarball 설치 테스트를 통과한다.
3. 시험 버전을 두 대표 소비자의 PR에서 검증한 후 정식 버전을 발행한다.
4. 앱은 명시 버전과 lockfile을 갱신하고 각자 배포한다. 운영에서 `latest`나 이동하는 Git branch를 직접 참조하지 않는다.
5. 회귀 시 앱의 직전 패키지 버전·lockfile·빌드 산출물로 되돌린다. 같은 버전의 패키지 내용을 바꿔 덮어쓰지 않는다.

SemVer의 공개 API에는 TypeScript 타입뿐 아니라 문서화한 정렬 기본값·키보드 동작·토큰 계약도 포함시키는 운영 규칙을 권고한다. `0.x`라는 이유로 무통보 파괴적 변경을 허용하지 않고, 소비 PR과 이관 지침을 갖춘다. 정식 안정화 후 비호환 공개 계약 변경은 major로 다룬다. [E7]

GitHub Packages는 scoped 이름과 설치 인증을 요구하며, 다른 저장소의 Actions가 읽으려면 해당 패키지 접근 권한도 필요하다. 따라서 비공개 운영에는 적합할 수 있지만 공개 패키지라도 무인증 설치 편의성을 기대하면 안 된다. npm 공개 배포는 공개 범위·라이선스가 확정된 뒤 비교한다. 토큰은 CI secret으로 관리하고 저장소나 컨테이너 이미지에 넣지 않는다. [E5]

담당자는 최소한 공통 API·릴리스 담당과 소비 앱 통합 담당으로 나눈다. 소수 인원이 겸임할 수 있지만 역할은 명시해야 한다. 긴급 수정은 먼저 실패를 재현하고 common 패치와 해당 앱 갱신을 연결한다. 임시 앱 복사가 필요하다면 종료 조건과 제거 작업을 함께 기록한다.

### 9. 라이선스와 코드 출처

조사한 루트 `LICENSE`는 geo·map·weather가 GPL v3 문서, concierge·docker-manager가 MIT였고 Pinvi는 루트 `LICENSE`를 찾지 못했다. 이는 파일별 권리·예외·제삼자 원본의 조건을 모두 확인했다는 뜻이 아니다. [L1]~[L5], [P6]

따라서 “같은 소유자의 프로젝트이니 새 common은 MIT로 하면 된다”고 단정할 수 없다. 기존 GPL 계열 코드에서 추출한 부분, 외부 primitive·템플릿의 원본, 기여자 권리와 고지를 확인해야 한다. GPL 라이브러리를 결합·배포할 때의 조건과 권리자의 별도 허락 가능성은 GNU FAQ를 참고한다. 기존 앱의 위반 여부를 이 소스 비교만으로 판정하지 않는다. [E8]

착수 시 파일별 출처 목록을 만들고, 원하는 공개·비공개 배포 모델에서 허용되는 라이선스를 확인한다. 비공개 registry 사용 자체가 재라이선스 권한을 만들어 주지는 않는다. 권리 확인이 끝나지 않은 파일은 추출 대상에서 보류한다. 이번 보고서 작업은 코드 이동이나 라이선스 변경을 수행하지 않는다.

### 10. 단계별 도입과 검증·철회 기준

| 단계 | 작업 | 완료 기준 | 중단·축소 조건 |
|---|---|---|---|
| 0. 계약 목록 | map·Pinvi 후보의 props·기본값·스타일·테스트·출처 비교 | 두 앱이 동일 의미로 사용하는 작은 후보와 의도적 차이를 문서화 | 제품별 분기가 다수 필요하거나 권리 확인이 안 됨 |
| 1. 작은 시범 | 토큰과 3~5개 작은 부품, map·Pinvi 각각 대표 화면 1개 이관 | 배포 tarball 설치, 타입·빌드·스타일·키보드 동작 통과 | 변경을 위해 각 앱에 우회 패치가 반복됨 |
| 2. 실제 공동 수정 | 공통 결함 한 건을 수정·릴리스하고 두 앱 반영 | 라이브러리 코드 복사 없이 수정 전파, 갱신 시간 기록 | common 수정·릴리스 비용이 복사보다 계속 큼 |
| 3. 복합 UI | DataTable 계약 합의 후 대표 목록 이관 | 서버/클라이언트 정렬, 선택·페이지 전환, 가상화·접근성 보존 | 여러 제품 전용 모드·도메인 API가 common 안으로 들어옴 |
| 4. 소비 확대 | geo의 호환성 해결, concierge·weather·manager 순차 평가 | 각 앱의 대표 기능 회귀·테마 검증과 되돌리기 성공 | React/스타일 업그레이드가 범위를 압도하면 해당 앱 보류 |
| 5. 안정화 | 공개 API·지원 범위·폐기 정책 확정 | 공동 사용 경험과 측정 자료로 안정 버전 결정 | 버전 분산·임시 복사본 누적 시 공유 범위 축소 |

시범 검증은 다음 실패를 실제로 잡을 수 있어야 한다.

- **버튼·폼**: 기본 submit 여부, Enter/Space·더블클릭, 진행 중 중복 제출 차단, ref, disabled 설명.
- **overlay**: 키보드 열기·닫기, 포커스 이동·복귀, portal 테마, 스크롤 잠금과 중첩 동작.
- **테이블**: 서버 페이지 부분 정렬 방지, 안정 행 ID, 선택 유지·초기화, 오류·빈 상태, 접근성 구조, 가상화 스크롤.
- **테마**: 밝은/어두운 모드가 있는 앱의 두 모드, 브랜드별 포커스·오류 표현, 좁은 화면, Pinvi 사용자 화면의 스타일 변화 없음.
- **배포**: 실제 tarball의 타입·CSS·client 지시문, React 중복 없음, SSR·hydration, 소비 앱 CI의 registry 설치와 버전 되돌리기.

common 자체 테스트, 소비 앱의 lint·타입 검사·단위 테스트·production build, 대표 화면 브라우저 검증을 구분한다. geo 이관 때는 기존 backend gate와 React Doctor·브라우저 검증 규칙도 적용한다. 라이브러리의 자체 성공만으로 여섯 앱이 호환된다고 선언하지 않는다.

### 11. 비용 추정과 최종 판단 기준

다음은 **실측 견적이 아닌 계획용 범위**다. 기존 두 앱에 익숙한 개발자 1인, 범위가 작은 시범, 큰 프레임워크 업그레이드 없음이라는 가정이다. 코드 출처 확인 대기·리뷰 대기·운영 배포 일정은 별도다. 인일은 실제 투입량이며 달력상의 완료일을 뜻하지 않는다.

| 작업 | 계획용 투입량 |
|---|---|
| 후보 계약·테마·출처 조사 | 2~4인일 |
| 두 패키지 최소 빌드·릴리스·설치 검증 구성 | 2~4인일 |
| 작은 부품 3~5개와 두 앱 대표 화면 이관 | 3~6인일 |
| 공동 수정·회귀·되돌리기 검증 | 2~4인일 |
| **작은 시범 합계** | **9~18인일** |

DataTable 전체 이관, 여섯 앱 확대, React/Next 업그레이드, Python 공유, 인증 통합은 위 합계에서 제외한다. 이들은 시범 후 실제 차이를 기준으로 별도 산정해야 한다.

경제성은 다음 식으로 판단할 수 있다.

> 회수 기간(개월) = 초기 이관 시간 ÷ (월간 중복 수정·회귀 절감 시간 − 월간 common 유지·릴리스·소비자 갱신 추가 시간)

예를 들어 초기 96시간, 월 절감 24시간, 추가 운영 8시간을 **가정**하면 순절감 16시간으로 약 6개월이다. 순절감이 0 이하라면 이 방식으로 회수되지 않는다. 이 숫자는 측정 결과가 아니며 “라이브러리를 만들면 6개월 안에 이득”이라는 예측으로 쓰면 안 된다.

시범 전후로 같은 유형의 UI 수정에 대해 원본 수정 시간, 다른 앱 반영 시간, 검증 시간, 발생 회귀, 남아 있는 로컬 복사본 수를 기록한다. 두 소비자가 독립 버전을 유지하면서 공통 수정 한 건을 코드 복사 없이 반영할 수 있고, 추가 조정 비용을 뺀 순효과가 양수면 확대한다.

이번 검토에서 채택할 방향은 **공통 admin 표현부터 작은 패키지로 시작**하는 것이다. 구현 착수 때 확정할 항목은 코드 출처와 라이선스, registry·scope, 초기 부품 목록, 지원 React 범위, CSS 배포 방식, 유지보수 담당이다. SSO·공통 백엔드·전 서비스 모노레포는 이 도입의 필수 조건으로 두지 않는다.

### 12. 조사 근거와 검증 범위

#### 저장소 기준

아래 링크는 조사 시점 커밋에 고정한다. 조사 후 `main`이 갱신되어도 위 판단을 재검토할 수 있다. 패키지 선언·선별한 UI 코드·인증 경계·기존 작업 기록을 확인했으며 운영 환경의 화면·성능·실제 설치 호환성은 이번 문서 조사에서 시험하지 않았다.

| 저장소 | 조사 커밋 |
|---|---|
| `kor-travel-geo` | `daf079b56b5ab50342fde7d7e5042d4ae88163fc` |
| `kor-travel-map` | `c72456f6d9e6560637bacf71b3955e58af65c02e` |
| `kor-travel-weather` | `6003da995fa4b35799f9dadc406c6ba2878bfbae` |
| `kor-travel-concierge` | `7945305dd8bcb3eccae54e08b1205d565daa3661` |
| `kor-travel-docker-manager` | `862562dcbd6a70c5d00e8d1538264fafe5ed5f5c` |
| `pinvi` | `2396d657aee6700d83e76fd8e2f4924fa66cd77e` |

- [G1] [kor-travel-geo — kor-travel-geo-ui/package.json](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/kor-travel-geo-ui/package.json)
- [G2] [kor-travel-geo — docs/resume.md](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/docs/resume.md)
- [G3] [kor-travel-geo — kor-travel-geo-ui/components/ui/button.tsx](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/kor-travel-geo-ui/components/ui/button.tsx)
- [G4] [kor-travel-geo — kor-travel-geo-ui/components/ui/VirtualTable.tsx](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/kor-travel-geo-ui/components/ui/VirtualTable.tsx)
- [G5] [kor-travel-geo — docs/architecture/architecture.md](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/docs/architecture/architecture.md)
- [G6] [kor-travel-geo — kor-travel-geo-ui/lib/auth.ts](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/kor-travel-geo-ui/lib/auth.ts)
- [G7] [geo — 최근 로그인 일치화 검토 기록](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/docs/journal.md)
- [M1] [kor-travel-map — packages/kor-travel-map-admin/frontend/package.json](https://github.com/digitie/kor-travel-map/blob/c72456f6d9e6560637bacf71b3955e58af65c02e/packages/kor-travel-map-admin/frontend/package.json)
- [M2] [kor-travel-map — packages/kor-travel-map-admin/frontend/src/components/ui/data-table.tsx](https://github.com/digitie/kor-travel-map/blob/c72456f6d9e6560637bacf71b3955e58af65c02e/packages/kor-travel-map-admin/frontend/src/components/ui/data-table.tsx)
- [M3] [kor-travel-map — packages/kor-travel-map-admin/frontend/src/components/ui/button.tsx](https://github.com/digitie/kor-travel-map/blob/c72456f6d9e6560637bacf71b3955e58af65c02e/packages/kor-travel-map-admin/frontend/src/components/ui/button.tsx)
- [W1] [kor-travel-weather — packages/kor-travel-weather-admin/frontend/package.json](https://github.com/digitie/kor-travel-weather/blob/6003da995fa4b35799f9dadc406c6ba2878bfbae/packages/kor-travel-weather-admin/frontend/package.json)
- [W2] [kor-travel-weather — packages/kor-travel-weather-admin/frontend/app/tokens.css](https://github.com/digitie/kor-travel-weather/blob/6003da995fa4b35799f9dadc406c6ba2878bfbae/packages/kor-travel-weather-admin/frontend/app/tokens.css)
- [C1] [kor-travel-concierge — frontend/package.json](https://github.com/digitie/kor-travel-concierge/blob/7945305dd8bcb3eccae54e08b1205d565daa3661/frontend/package.json)
- [D1] [kor-travel-docker-manager — frontend/package.json](https://github.com/digitie/kor-travel-docker-manager/blob/862562dcbd6a70c5d00e8d1538264fafe5ed5f5c/frontend/package.json)
- [D2] [kor-travel-docker-manager — backend/src/kor_travel_docker_manager/api/auth.py](https://github.com/digitie/kor-travel-docker-manager/blob/862562dcbd6a70c5d00e8d1538264fafe5ed5f5c/backend/src/kor_travel_docker_manager/api/auth.py)
- [P1] [pinvi — apps/web/package.json](https://github.com/digitie/pinvi/blob/2396d657aee6700d83e76fd8e2f4924fa66cd77e/apps/web/package.json)
- [P2] [pinvi — apps/web/components/admin/ui/data-table.tsx](https://github.com/digitie/pinvi/blob/2396d657aee6700d83e76fd8e2f4924fa66cd77e/apps/web/components/admin/ui/data-table.tsx)
- [P3] [pinvi — apps/web/components/admin/ui/button.tsx](https://github.com/digitie/pinvi/blob/2396d657aee6700d83e76fd8e2f4924fa66cd77e/apps/web/components/admin/ui/button.tsx)
- [P4] [pinvi — packages/design-tokens/package.json](https://github.com/digitie/pinvi/blob/2396d657aee6700d83e76fd8e2f4924fa66cd77e/packages/design-tokens/package.json)
- [P5] [pinvi — apps/web/app/globals.css](https://github.com/digitie/pinvi/blob/2396d657aee6700d83e76fd8e2f4924fa66cd77e/apps/web/app/globals.css)
- [L1] [kor-travel-geo — LICENSE](https://github.com/digitie/kor-travel-geo/blob/daf079b56b5ab50342fde7d7e5042d4ae88163fc/LICENSE)
- [L2] [kor-travel-map — LICENSE](https://github.com/digitie/kor-travel-map/blob/c72456f6d9e6560637bacf71b3955e58af65c02e/LICENSE)
- [L3] [kor-travel-weather — LICENSE](https://github.com/digitie/kor-travel-weather/blob/6003da995fa4b35799f9dadc406c6ba2878bfbae/LICENSE)
- [L4] [kor-travel-concierge — LICENSE](https://github.com/digitie/kor-travel-concierge/blob/7945305dd8bcb3eccae54e08b1205d565daa3661/LICENSE)
- [L5] [kor-travel-docker-manager — LICENSE](https://github.com/digitie/kor-travel-docker-manager/blob/862562dcbd6a70c5d00e8d1538264fafe5ed5f5c/LICENSE)
- [P6] [Pinvi 루트 트리](https://github.com/digitie/pinvi/tree/2396d657aee6700d83e76fd8e2f4924fa66cd77e): 조사 커밋의 루트 `LICENSE` 부재 확인.

#### 외부 공식 문서

- [E1] [Tailwind CSS 소스 탐지](https://tailwindcss.com/docs/detecting-classes-in-source-files): 외부 패키지·명시적 소스 등록·클래스 탐지.
- [E2] [npm package.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/): peer 의존성과 배포 파일 계약.
- [E3] [Next.js 서버·클라이언트 컴포넌트](https://nextjs.org/docs/app/getting-started/server-and-client-components): client 경계와 라이브러리 작성 시 지시문 보존.
- [E4] [Node.js 패키지 진입점](https://nodejs.org/api/packages.html#package-entry-points): `exports`와 공개 하위 경로.
- [E5] [GitHub Packages npm registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry): scope·인증·저장소 간 접근.
- [E6] [Next.js transpilePackages](https://nextjs.org/docs/app/api-reference/config/next-config-js/transpilePackages): 로컬·외부 패키지의 소스 변환.
- [E7] [Semantic Versioning 2.0.0](https://semver.org/): 공개 API와 호환성에 따른 버전 규칙.
- [E8] [GNU 라이선스 FAQ](https://www.gnu.org/licenses/gpl-faq.en.html): 라이브러리 결합·배포와 권리자의 라이선스 선택.

외부 문서는 2026-09-05 확인 기준이며, 실제 패키지 구현 시 지원 버전·registry 정책을 다시 확인한다. 위 기술 문서는 본 보고서의 패키징 권고를 뒷받침하며 특정 앱의 현재 운영 안전성을 보증하지 않는다.
