# 공통 라이브러리 비교·구현·검증 통합 보고서

작성 기준: 2026-11-12 한국시간. 최신 Transport 요구인 Geo형 모바일 Drawer·PC 세로 rail의 실제 정상9/9검사 PASS를 부모가 독립 확인했다. 현재 운영은 PR186 merged f30dbd823614399d6dc671eb1f1bf4d8f46c6064 / ARM image sha256:0ac648f860f7aba501ad6ff1b6f4457344e0ed91ebd60a2d1a9a4338b97be69b다. 6개 앱의 배포·실제 수용을 확인한 범위와 Map 사용자 제외를 유지한다. owner 최종 영수증·63개 index 검산과 [Common50](https://github.com/digitie/kor-travel-common/pull/50) 병합678a5bcf를 확인했다. 최종 실제 수용은 [공개6개 앱 배포 영수증](https://github.com/digitie/kor-travel-common/blob/678a5bcf0150ac0386bfa86106e7e0f4f77e8639/docs/reviews/adversarial/evidence/2026-11-12-frontend-deployment-receipt.json)과 연결한다. 이 단일 MD의 최종 사실 delta는 기존 원 A/B와 정확 CI 검토 대상이며, 후속 빌드 생태계·CI/테스트 통일·최후 CI 순서 최적화는 미완료다.

최종 source bd08·CI 합성8303·merged f30의 전체 tree는4fec4f76df0cd88fdaca22d42ae2acb2f876ce6f로 같다. 정상 ARM docker build6.6초의 같은 tree cache 재사용은 retag가 아니며 source909/COPY298/Common263/routes32·승인 키·환경·OCI/default M strict 검증을 통과했다. SDK508 dry-run1/confirm1·오류0·healthy/current/postproof와 부모의 원격44개 원문 검산을 완료했다. 선택된 Transport 관리자 current는 새 tuple로 갱신하고 타54개·공개936·backend499/schema0042·auth/env/pin 및 타 앱 current는 보존했다.

새 M의 정상 세션은 로그인1/로그아웃1·전체9검사 PASS·오류0·브라우저 종료다. 실제 수신 PNG는 카메라 이동 전2개/후2개를 createImageBitmap으로256×256 decode했고 zoom7→8을 확인했다. Pretendard custom glyph12표본(표1+반응형11),9개 고유 폭/11전환을 확인했다. PNG cleanupComplete·pending0/expired0/errors0을 검산했다. 부모는 지도1장·메뉴3장을 직접 보아 한국 도로·지형·labels/zoom8, PC256px 세로 rail·모바일296px left Drawer의 가독성을 확인했다. 지도 screenshot의 일부 업무 query pending 표시는 별도 업무/API 검사 PASS와 구분한다.

새로 승인·검토한 UX5/total60 계약에서 feedback2.808995초·bootstrap 준비5.644271초와 양쪽 own loader0을 관찰했다. **이는 기존 early-canvas5초 조건을 완화한 다른 계약의 PASS이며 성능 개선 주장이 아니다.** 이전 M9의 첫8PASS/1FAIL과 PNG-only 진단1FAIL, 그 당시 형식/크기 검사45개·19개(실제 decode 아님), canvas10.351초/child handle15.969초를 원문 그대로 보존한다. 새5.644초를 이 과거 값과 인과 비교할 수 없다. 당시 M885→M9 초기 JS raw+10bytes/gzip−71bytes만으로 size bloat를 원인으로 설명하지 않으며, No-JS loader 표시 면적0의 교정 동기 측정1회와 원 비동기 observer45초 실패도 각각 다른 증거로 남긴다.

원 A/B Source2/helper3/final EXEC4는 최종 PASS·신규0이며 문서 P3를 수정했다. PR/push/policy3CI 모두 SUCCESS, backend 각1548PASS/기존2SKIP/6warnings(2390초·2479.74초)이고 live-e2e2SKIP은 PASS에 합산하지 않는다. local Native43/Alpine43은 각각 first PASS다. 아직 실행하지 않은 native 기기·EAS·스토어 배포, 후속 Transport 잔여PR/빌드 생태계·프로젝트 간 CI/테스트 정합성은 미완료다. CI 순서·fail-fast 최적화는 맨 마지막에 수행한다. 키 값·운영 호스트·private 경로는 출판하지 않는다.

## 1. 최종 결정과 적용 범위

공통화의 단위는 접근성·상호작용·디자인 토큰·의존성 정책이다. 앱별 데이터 조회, 도메인 권한, 라우팅, 인증 세션과 운영 배포 책임은 각 앱이 유지한다. 사용자 요구에 따라 shadcn/ui Radix, 모든 관리 표의 공통 VirtualTable, Tailwind4.3.5, RHF·Zod·Zustand·Pretendard의 실제 사용을 반영했다. 설치 목록만 추가한 상태는 수용으로 세지 않는다.

비교 표면은 기존 조사와 같은 **10개 package.json**이다. Geo·Map admin·Weather·Concierge·Manager·Pinvi web/admin·Pinvi mobile·Transport public/admin의 앱 표면 9개와 Map SDK 1개다. Pinvi의 웹 공개 화면과 관리자는 같은 앱 패키지에 포함된다. Map SDK는 독립 UI나 운영 서비스가 아니므로 배포 프로젝트 수에 더하지 않는다.

| 공통 영역 | 확정된 구현·버전 | 앱이 유지하는 책임 |
|---|---|---|
| 웹 엔진 | React/DOM19.3.1, Next16.4.6, Tailwind 및 PostCSS 플러그인4.3.5, PostCSS8.5.32 | 라우트·서버/클라이언트 경계·앱별 빌드 설정 |
| 컴포넌트 | @kor-travel/ui0.2.0의 shadcn/ui Radix 프리미티브·overlay·공통 로그인·Dagster UI | 도메인 필드·작업·인가·데이터 연결 |
| 표 | 공통 VirtualTable, TanStack Table9.3.1·Virtual3.14.26 | 서버 정렬/페이지·행 키·선택 권한·도메인 셀 내용 |
| 폼·상태 | RHF7.92.0, Zod4.6.7, Zustand5.1.0, resolver7.0.5는 사용하는 앱에서 일치 | 입력 스키마·제출 API·서버 캐시·상태 수명 |
| 토큰·폰트 | @kor-travel/tokens0.1.1, Pretendard1.3.9, 의미 토큰·웹 CSS bridge | 앱 브랜드·레이아웃·데이터 시각화 의미 |
| 지도 | vworld-map-core1.0.1/web1.0.3/RN1.0.1, 웹 MapLibre6.17.0 | 중심/범위·업무 geometry·API 결과·플랫폼 어댑터 |
| 품질 | ESLint10.14.0, React Doctor0.9.22, 타입·단위·production browser·중앙 정책 CI | 의미 있는 회귀 단언·예외 근거·정확 소스와 증거 연결 |
| 모바일 | Expo58.0.24, RN0.88.1, NativeWind5.0.0-rc.1, react-native-css3.1.0-rc.1 | native UI·Metro/Babel·export·실제 기기 수용 |

웹 공통 UI는 DOM/Radix 계약이다. Pinvi native에는 DOM UI나 개별 Radix를 넣지 않고 tokens·RHF·Zod·Zustand·실제 native 폰트와 지도 RN 어댑터를 적용했다. Manager와 Transport 공개 웹은 지도 기능이 없어 지도 패키지를 추가하지 않았다. 모든 앱의 도메인 의존성 목록을 같게 만드는 정책은 아니다.

## 2. 최종 병합 소스와 기준선

아래 7개 주 PR은 모두 병합되었다. 로컬 Git object에서 각각 검토 HEAD와 merged SHA의 **전체 tree 동일성**을 다시 확인했다. 후속 Manager SDK589/590은 이 7개 주 PR과 구분한다. Map1496 병합은 역사적 사실로 보존하며 사용자 제외 지시를 이유로 되돌리지 않는다.

| 프로젝트 | 주 PR | 최종 merged SHA | 검토 HEAD | 전체 tree |
|---|---|---|---|---|
| Geo | [631](https://github.com/digitie/kor-travel-geo/pull/631) | 786dae25f0a1927a98cbc66e6e8c86987da0a42f | 12bff3df | 동일 |
| Map | [1496](https://github.com/digitie/kor-travel-map/pull/1496) | f347b353fb13fe83ffbdfdacb894b2bfa9ebcb87 | 7ce46cd9 | 동일 |
| Weather | [226](https://github.com/digitie/kor-travel-weather/pull/226) | faca2ceee39a116dfea0680e2a5e1d8ced198cf1 | 2b34884c | 동일 |
| Concierge | [265](https://github.com/digitie/kor-travel-concierge/pull/265) | f2db107cc4bfb58115b890ea6198a2fe0c321e17 | 76beb95c | 동일 |
| Docker Manager | [588](https://github.com/digitie/kor-travel-docker-manager/pull/588) | 9910b9a6dba902c6a59469d3a6f46c6077e78d3f | 158db1ab | 동일 |
| Pinvi | [732](https://github.com/digitie/pinvi/pull/732) | dd3bcd18ce573e6ddf784864d63901352e7e05d3 | 528d8254 | 동일 |
| Transport | [181](https://github.com/digitie/kor-travel-transport/pull/181) | 936fdb90b0ee9f6392d2f888255053ee1f4066b2 | 4e25c98e | 동일 |

Pinvi는 저장소가 허용하는 squash 방법으로 병합했다. 이전 PR 합성 merge의 SHA를 실제 checkout으로 간주하지 않는다. 검증한 source/tree와 이미지의 OCI revision·고유 ENV를 대조하는 계약을 별도로 적용했다.

## 3. 장점과 비용: 이번 통합에서 확인한 결과

| 장점 | 실제 근거 | 남는 비용·한계 |
|---|---|---|
| 같은 상호작용 수정의 재사용 | 공통 Dialog 포커스·Tabs 방향/숨김·로그인 SSR/자동완성 수정이 여러 앱에 반영됨 | 공통 런타임 변경은 여러 소비자의 회귀 범위를 넓힌다 |
| 표의 의미·접근성 계약 통일 | 공통 header/cell/scope·alignment·region·선택 권한·가상화 사용 | 앱이 불안정한 셀 컴포넌트나 행 identity를 주면 DOM remount가 생길 수 있다 |
| 폼의 오류·제출 일관성 | RHF/Zod 공통 로그인과 실제 입력·제출 회귀 | 이메일/아이디·역할·쿠키 세션은 앱별 계약이므로 하나의 인증 엔진으로 합칠 수 없다 |
| 토큰과 실제 폰트의 일관성 | 의미 토큰·공식 Tailwind variants·Pretendard 웹/native 로드 | CSS import 순서·앱 테마·native 스타일 변환은 별도 검증이 필요하다 |
| 버전·동일 bytes의 추적 가능성 | canonical ledger·lock SRI·실제 설치 파일·실제 이미지 파일 비교 | 같은 이름 tgz 캐시, override 중복·workspace hoist 검증 비용이 생긴다 |
| 원본 버그 수정의 재사용 | VWorld·Lightning CSS/serde-content·FocusScope를 원 소스에서 수정·고유 버전으로 배포 | fork 유지·원본 동기화·대응 소스/라이선스 보존 책임이 생긴다 |
| 퇴행을 조기에 거부 | 로컬 guard·중앙 exact code CI·Doctor warning gate·provenance negative control | 규칙 자체도 실제 공격/정상 입력으로 검증하고 공통 정책 변경의 소비자 영향도 확인해야 한다 |
| 배포 결과의 분리 | CI 이미지·최종 merged 이미지·공식 활성화·실제 UI 수용을 각각 기록 | CI 성공만으로 운영 로그인·지도·세션 종료를 대신할 수 없다 |

이번 작업은 공통 패키지가 소비 앱 오류를 자동으로 없애지는 못한다는 점도 확인했다. Concierge 셀 컴포넌트 remount, Pinvi의 이미지 revision 오표기와 존재하지 않는 CI 경로, 모바일 SDK patch drift는 앱에서 고쳤다. 공통 버그는 원본으로, 앱 상태·도메인·CI 오류는 해당 앱으로 되돌려 수정 범위를 지켰다.

Transport 후속 이관은 이 비용을 구체적으로 보여 준다. 운영 관리자6bd의 독립된 기능44파일과 /parking-lots·/rail/timetable 두 경로를 최신 공통화936에 합집합으로 보존해야 했으며, 공통 bytes 일치나 Doctor0만으로 기존 기능 보존을 보장하지 못했다. 원 독립 리뷰는 공식 철도 안내·전화 링크의 소실, 집계 count를 포함한 cluster key로 인한 DOM 정체성 소실, 한국어 작업명 누락을 찾았다. c3da263에서 공식/전화 링크·안정 좌표 key·한국어 label을 복구했고, 이후 같은 소스의 native/Alpine 실행56개와 원 A/B 최종 source+QA 검토까지 통과했다. 이 결과도 실제 ARM 운영 이미지·정상 인증 수용을 대신하지 않는다.

동일한 라이브러리 version/bytes만으로 앱별 CSS·모바일 메뉴 UX·운영 설정·키 선택이 자동으로 일치하지는 않는다. 정본의 strip 기본값·Geo drawer 허용 옵션과 실제6개 앱의 UI는 구분해야 한다. common component의 실제 통합·UI 회귀와 운영 입력 선택을 검증해야 하며, 설정 alias 이름이나 HTTP200만으로 동일 입력·유효 지도 이미지를 가정할 수 없다.

비용 절감률·장기 유지보수 시간·성능 향상률은 측정하지 않았다. 실제 확인한 이익은 중복 구현의 제거, 동일 회귀의 공동 수정, 정확 버전·소스·산출물의 추적 가능성이다. NativeWind RC의 안정성과 실기기 동작은 export 성공만으로 확정하지 않는다.

## 4. 구현 경계와 재발 방지

### 4.1 공통 UI·표·폼·상태

- Base UI/Floating UI 및 앱별 Radix overlay 구현을 공통 shadcn/ui Radix 경로로 이관했다. 공통 Badge tone, Alert warning/info/success, Dialog size·한국어 닫기, 서버에서 호출하는 순수 CVA variant도 공통 API가 소유한다.
- Tabs orientation 전달, forceMount된 비활성 MapTabPanel의 실제 hidden 처리, focus-visible 스타일과 공식 CSS custom variants를 반영했다.
- VirtualTable은 hideHeader에서 실제 thead를 제거하고 scope·정렬·region·data-slot 계약을 제공한다. 선택 predicate·bulk 작업 권한·상세 행 key namespace와 Geo SSE 셀 수명을 수정했다.
- Concierge CandidateTable은 header/cell을 모듈 범위의 안정 컴포넌트로 두고 현재 선택 상태·동작을 meta로 전달한다. selected 의존 useMemo로 컴포넌트를 다시 만드는 방식은 사용하지 않았다. 원래 재현에서 header/row Space 뒤 node disconnect·BODY focus를 확인하고 같은 회귀를 DOM identity·focus 보존으로 닫았다.
- Geo Button은 공통 Button·서버용 순수 variant에 실제 위임하고, Map wrapper의 variant/size 전달 회귀도 기존 source에서 수정했다. 같은 이름만 유지하는 복제 primitive를 공통 재사용으로 세지 않는다.
- 공통 LoginForm의 SSR defaultUsername, hydration 준비 상태, 자동완성 FormData→RHF 동기화·중복 제출을 검증했다. 비밀번호나 인증 쿠키를 전역 Zustand에 보관하지 않는다.
- 상태 구독·관심사 분리·native semantics를 실제 수정해 Doctor 진단을 없앴다. 광역 off나 ignore baseline으로 경고를 숨기지 않았다. 순차 브라우저 조작 등 정당한 false positive는 해당 줄과 근거를 남긴 국소 예외로 제한한다.

### 4.2 토큰·스타일·플랫폼

토큰은 색·타이포그래피·간격·radius 등 의미를 공유하며 제품별 브랜드와 화면 구성은 유지한다. 웹은 tokens/font.css의 로컬 Pretendard와 tokens/radix.css의 Tailwind4 `--color-*`·radius bridge를 사용한다. radix.css는 공식 shadcn custom variants와 tw-animate-css를 포함하며 앱의 로컬 테마보다 앞에서 가져와 override 순서를 명확히 한다. shadcn에서 가져온 코드·CSS는 MIT 출처/원문 고지를 동봉한다.

모바일은 tokens 데이터와 네 개 native OTF의 실제 로드를 사용한다. DOM CSS bridge나 DOM FocusScope를 native 그래프에 직접 요구하지 않는다. Pinvi .native/.web 어댑터는 RN과 웹 지도를 분리하고 웹 지도는 SSR 단계에서 브라우저 객체를 만들지 않도록 지연 로드한다.

### 4.3 의존성·소스·CI 정책

| 검사 경계 | 실제 강제 내용 | 놓치지 말아야 할 점 |
|---|---|---|
| 정본 | common versions.json의 axes + frontendPolicy에서 frontend-dependencies.json·내장 정책을 생성 | 과거 일반 버전 예외 설명과 이번 exact frontend 정책을 혼동하지 않는다 |
| 웹 로컬 검사 | UI의 check-dependencies.mjs와 `--artifacts common-artifacts.json` | workspace lock·실제 경로·소스 범위까지 검사 |
| 모바일 로컬 검사 | tokens의 checker에 `--profile mobile`·root lock·apps/mobile workspace 지정 | native에 DOM UI를 넣지 않고 필수 native 축을 검사 |
| 실제 소스 검사 | 일반 src/app/components/lib 자동 탐색 또는 정확한 `--source` | 탐색할 소스가 없으면 실패, HTML 표·private import·재export 우회 검사 |
| 설치·lock | 선언 exact·실제 도달 그래프·중복 React·alias·workspace 개발 의존성·tgz SRI 검사 | package.json만 맞아도 실제 stale 파일이면 완료가 아니다 |
| 중앙 reusable CI | 코드55a921b55d248106cbe320e7f5305f3d3cdb60fe 고정, 정책/원장은 현재 common main 데이터와 대조 | 코드 실행 ref와 정책 데이터 ref를 구분하고 실제 데이터 SHA 기록 |
| ESLint·React Doctor | ESLint10.14.0, Doctor0.9.22 `--scope full --blocking warning` 필수 | 기존 경고도 해결, no-new만으로 완료 처리하지 않음 |
| 모바일 SDK 진단 | Expo Doctor20/20 필수, informational continue-on-error 제거·aggregate 연결 | React Doctor0과 서로 다른 검사 |
| 이미지 provenance | git rev-parse HEAD를 expected PR/push SHA와 비교한 단일 revision 사용, OCI+고유 ENV 실제 inspect | 다른 유효40hex label도 거부하는 실제 negative control |
| CI 경로 | 존재하지 않는 apps/mobile/vendor 두 경로 제거, 실제 apps/web 공유 vendor 감시 유지 | 빈 가짜 폴더·skip·단언 약화로 green을 만들지 않음 |

필요 라이브러리·사용 계약의 정본은 [Common 최종 frontend-libraries 규약](https://github.com/digitie/kor-travel-common/blob/678a5bcf0150ac0386bfa86106e7e0f4f77e8639/docs/standards/frontend-libraries.md)이다. 이 문서의 전체412개 직접 선언 비교와 실제 수용 범위는 해당 정본·공개 영수증을 함께 읽는다.

중앙 정책 데이터가 갱신되면 이전 소비 소스의 검사가 달라질 수 있다. 재현하려면 검사 코드 SHA뿐 아니라 실제 policy/ledger 데이터 SHA도 보존해야 한다. 데이터가 이동한다는 이유로 실행 코드를 moving ref로 바꾸지는 않는다.

공통 source scanner는 일반 기본 경로 밖의 소스를 위해 명시적인 --source도 받는다. Pinvi 웹 로컬 검사의 관리 UI 범위와 전체 앱 Doctor·브라우저 범위를 구분한다. Map SDK에는 DOM UI 정책을 강제하지 않는다.

ESLint10을 지원하는 typescript-eslint·Next plugin·import-x·react-x/react-dom·jsx-a11y-x 조합으로 옮겼다. ESLint 구버전 peer를 `--legacy-peer-deps`/`--force`로 무시하지 않았다. Expo 모바일 lint도 실제 새 조합에서 검증했다. Doctor의 실제 CLI 옵션과 각 앱 script를 확인했고 버전에 없는 옛 AGENTS 명령을 그대로 실행한 것으로 기록하지 않는다.

TypeScript5.9.3은 openapi-typescript의5.x 및 typescript-eslint의 <6.1 peer 때문에 유지했다. Babel7.29.7은 Expo58 플러그인 peer 계약에 따른 호환성 선택이다. TypeScript7·Babel8을 검증한 것으로 기록하지 않는다. Pinvi/Map workspace의 npm12.0.1 고정은 실제 Node22 소비 환경 및 lock 생성 도구와 함께 기록한다.

## 5. 원 라이브러리 결함 수정과 출시 산출물

### 5.1 VWorld 지도 원본

조사 시작 GitHub source9c46c57181d433c91f7e8837c4e4396204e9b583에서 원본 수정9a7a348b02d61969b394c681b024d5851eef836b로 이동했다. [VWorld PR32](https://github.com/digitie/maplibre-vworld-react/pull/32)는 ae1e209967b3be7a3918f44e4df278add9f1376c에 병합되었고 전체 tree가 검토 소스와 같다.

상위 tsconfig의 ES6 target에서 Object.entries 타입 오류가 나던 것을 ES2022로 고쳤다. public mapStyle을 제공해 키 없는 로컬 geometry 지도를 허용하며 style 교체 때 map instance를 보존했다. 패키지 public export·CSS·worker·라이선스/대응 소스를 검증했다. source browser19·packed browser19·RN21 및 정확 소스 CI가 통과했다. 웹 ESM의 CSS를 일반 Node import로 읽을 때의 확장자 오류와 실제 번들러의 CSS 소비를 구분했다.

core/RN1.0.1과 web1.0.3을 적용한 과거 Map1496 결과는 보존한다. **사용자 제외 이후 이 문서 작업에서 Map 소스·이미지 빌드·adopt·apply를 수행하지 않는다.** Pinvi 공식 paired 배포 중 기존 fd1 Map pin을 보존해 재구축한 이력은 Map 최종 공통 UI 배포 수용으로 집계하지 않는다.

### 5.2 Lightning CSS·serde-content

Expo58·RN0.88.1·NativeWind5 RC1의 실제 Android export에서 Lightning CSS1.33.0 visitor 역직렬화 오류를 재현했다. 원본 Lightning CSS와 serde-content의 null option·Infinity·큰 정수 변환을 수정했다. 구버전1.30.1로 되돌린 상태를 최종 해결로 삼지 않고 고유 버전1.33.0+nativecss.fix.4로 고정했다.

GNU native와 같은 입력 소스의 WASM을 한 pack에 동봉했다. 특수문자 경로(공백/#/%) 로더, MIT 고지, 실제 소스/binary 계보, Windows fixture를 원 A/B 지적에 따라 보완했다. Rust126·Node native90/WASM90·실제 앱113 클래스 compiler IR8 입력의 정상 비교, Ubuntu·Windows·macOS Intel CI와 actual native/WASM 소비를 확인했다. macOS ARM runner 취소를 성공으로 합산하지 않는다. [Lightning PR1](https://github.com/digitie/lightningcss/pull/1)과 [serde-content PR1](https://github.com/digitie/serde-content/pull/1)은 각각 f24bb66·21d1c7로 병합되었고 검토 tree 동일성을 확인했다.

### 5.3 Radix FocusScope

초기 패널에 포커스가 있을 때 Shift+Tab이 마지막 입력으로 이동하지 않는 결함과 disabled fieldset의 비활성 입력을 후보로 고르는 상속 결함을 원본 helper에서 수정했다. 모든 disabled fieldset 조상의 첫 직접 legend 예외·동적 enable/disable·중첩 scope·IME 처리를 보존했다. 앱별 Tab trap이나 node_modules 임시 수정으로 우회하지 않았다.

source1752a539c8d5ae57961a0fa2702d2573d48fefe7, frozen delivery01e8181f6fc73fac6aeb140cac96dcdb30f8aaa6의 공식 scoped package `@radix-ui/react-focus-scope@1.3.1+kortravel.fix.2`를 사용한다. 같은 source38개는 fix.1에서32PASS/6FAIL→fix.2에서38PASS, 실제 packed browser17개는10PASS/7FAIL→17PASS다. 원 A의 actual packed browser20개·원 B의 CJS/ESM 각각38개와 네 CI 모두 PASS/신규0이다. [Radix PR1](https://github.com/digitie/radix-primitives/pull/1)은408bb40dcc90d806d2fd55a9360a5a11e599e157에 병합되었다.

### 5.4 C11 최초 릴리스·동일 bytes·라이선스

[Common PR49](https://github.com/digitie/kor-travel-common/pull/49)는 reviewed2d4579에서 main e8ed3ae75000be5cd22a3a11492bd97660635d78로 병합되었다. C11 producer는 a35481349d6747b4f13b958ae64d9c0bbd0b5413이며 **공식 최초 릴리스 이후 아래 bytes는 불변**이다. 후보 원장의 `CANDIDATE_NOT_RELEASED` 문구는 pack 당시 역사적 메타데이터다. 릴리스 완료를 이유로 기존 tgz나 원장을 다시 pack/수정하지 않았다.

C10→C11의 일반 파일119개 중 정책JSON2개만 바뀌고117개는 byte 동일하다. 외부 FocusScope 런타임 자체는 fix.2로 바뀌었으므로 실제 최종 modal·브라우저 검증은 다시 수행했다. 같은 filename의 file: 패키지는 명시 전체 설치로 lock integrity를 갱신하고 UI/tokens119파일+Scope15파일을 실제 대조했다. 소비 범위에 따라 Manager/public153, 지도 웹263, Pinvi297파일로 검증 범위가 다르며 파일 수를 단순 합산하지 않는다.

| 배포 패키지 | 정확 버전 | bytes | SHA256 | 라이선스 |
|---|---|---:|---|---|
| @kor-travel/ui | 0.2.0 | 71903 | 16b4c213453fb02b527f8e4ae673a703e4ba3808538ae6fb24f70bdda770d213 | GPL-3.0-or-later |
| @kor-travel/tokens | 0.1.1 | 34132 | 7e88aaf70b93fed953198779fd17a003e327499e686794fd5f647b23cc325ad3 | GPL-3.0-or-later |
| vworld-map-core | 1.0.1 | 18236 | 36d3ba16a3ba65f7a460db6027c07e29821f2795b15a526413949210f0ce92b6 | GPL-3.0-only |
| vworld-map-web | 1.0.3 | 88106 | 1ab9af8794979a5a19e5ac635cd04a9e87b9847058eaf4e9df743143b8ad4104 | GPL-3.0-only |
| vworld-map-rn | 1.0.1 | 25225 | 352307615edad047cc100cff6a39c625e778f77434b48475c9930e25ca7b6404 | GPL-3.0-only |
| lightningcss | 1.33.0+nativecss.fix.4 | 15376394 | 12c8326428a56e38231f7b5b376df0c6882e3492da794f3499269628edcaccf0 | MPL-2.0 |
| @radix-ui/react-focus-scope | 1.3.1+kortravel.fix.2 | 33511 | 1ca04870692565c243130d99c3dba91f3ac853ab2ec9538fc7b658b17fb7b49a | MIT |

원장의 producer/source 식별자는 다음과 같다. source와 이후 리뷰·CI·병합 커밋의 차이는 대응 tree·archive 증거로 연결한다.

| 원장 source | 고정 commit |
|---|---|
| common | a35481349d6747b4f13b958ae64d9c0bbd0b5413 |
| maplibre-vworld-react | 9a7a348b02d61969b394c681b024d5851eef836b |
| lightningcss | 748651cbd845971e65c411166ddee101745dab21 |
| serde-content | 18e53fcf6f8ace093a292891b34fa3411192617d |
| radix-ui-primitives | 1752a539c8d5ae57961a0fa2702d2573d48fefe7 |

각 pack은 해당 사용 앱의 vendor·원장·lock SRI와 일치시킨다. 아래 SRI는 final C11 실제 파일에서 대조했다.

<details>
<summary>C11 7종 SHA512 SRI</summary>

- @kor-travel/ui: `sha512-BsRRdnJUp6FQ2KWkXtINb7IkrxxwnWFlLP/oVlNN4UXBKren7uTlnYT4iJsdaO98iA4Tn2EMPX06eT2uB5jEDA==`
- @kor-travel/tokens: `sha512-85mqNJXqhTlA4RbtKUhmzx6rH6mOOeNmsXTJtCetQ5y8njLy+5XLZbdT6j1tf3ME9XQA6X63Ah4kmuLdqEZHbA==`
- vworld-map-core: `sha512-Djm14Arr7U0r7Sabj6P0V57CdzWIGaJmecklmY1hwrq1QUZJjMUFgkZfGRFalUo6AFzHEwwzOEzbJPMifGhINw==`
- vworld-map-web: `sha512-HPXZcz/wP6tFsCZqlAbansWNICcZPubC+/V7rDWXYTQVlOBLl9cZQ1HSMJd25c2CZoMNreVFTQA0vzkVglkS1w==`
- vworld-map-rn: `sha512-lgDBasKIEG2ElQ9jnHDB9pA+x04Xge9yzBb1NPPw1auyvlkQvxsq4NfRPIrw1VWiutcGiIefySLiVaZDUkO69Q==`
- lightningcss: `sha512-zDQ03VJE37OlyBrLsRcsEdIVu0T4BXJKDH5y9//To6GlGN2UrKQGERFVAFblkPQ5ZEbhuOp5wpXxGARZNdbQLA==`
- @radix-ui/react-focus-scope: `sha512-v3XweXrUSZ/QfrMVvYmsAkVNDnvcN21QKbSrViXYf0OQf5Ue9xSgqQIukgGjsYMEBQ5qxQW8fnOC9t1Y0ENPXw==`

</details>

Common UI/tokens 자체는 GPL-3.0-or-later다. 내장한 shadcn/Radix MIT 고지는 별도로 보존하며 전체 패키지를 MIT로 오기하지 않는다. VWorld3종은 GPL-3.0-only, Lightning CSS는 MPL-2.0, FocusScope는 MIT다. 필요한 LICENSE/NOTICE/SPDX·대응 소스·provenance와 실제 배포 archive 검사를 함께 유지한다. 공통화가 서로 다른 원본의 라이선스를 없애지는 않는다.

## 6. Pinvi 모바일: 최종 SDK 패치와 검증의 경계

기준선 Expo57/RN0.86.3/NativeWind4/Tailwind3에서 최종 Expo58/RN0.88.1/NativeWind5 RC/Tailwind4로 이관했다. 이관 체크포인트328의 Expo Doctor는19/20였고 workflow informational SUCCESS와 구분해 실제 버전 표를 조사했다. 마지막4종은 RC peer를 이유로 무시할 문제가 아니라 다음 patch drift였다.

| 모바일 전용 SDK 패키지 | 중간 체크포인트 | 최종 병합 dd3 exact |
|---|---|---|
| expo | 58.0.23 | 58.0.24 |
| expo-constants | 58.0.15 | 58.0.16 |
| expo-linking | 58.0.16 | 58.0.17 |
| expo-router | 58.0.30 | 58.0.31 |

이4종은 common의 관리 axes/packages/profile 필수 축이 아니다. 모바일 package·물리 설치 stage·root lock과 해당 root expo/router 선언을 함께 갱신했다. C11 UI/tokens 재릴리스나 C12를 만들지 않았다. 공통으로 관리하는 React/RN/NativeWind/Tailwind/CSS 엔진 축은 exact를 유지했다.

최종528(merged dd3와 동일 tree)에서 필수 Expo Doctor20/20, React Doctor0, type/lint·중앙 정책, Android/iOS/WebSSR export·네 OTF·375/1280px CSS/폰트/입력 스모크, 실제 macOS 강제WASM export를 확인했다. GitHub CI의 합성 merge77afd9도 전체 tree가528과 같다. **실제 native 기기 실행·EAS·스토어 출시는 NOT_RUN**이다.

## 7. 검증·리뷰·운영 배포 현황

### 7.1 최종 source 검증

| 대상 | 최종 확인 결과 | 해석 |
|---|---|---|
| Common | UI101·tokens9·정책175, 도구399PASS/1SKIP, Doctor80파일0, 실제 packed browser65·webpack/Turbopack·4workflow/docs6job SUCCESS | 원 Common7 A/B PASS/신규0; 과거 BLOCK/CONDITIONAL 원문 보존 |
| Geo | actual263·guard/peer tree·단위294·lint/type/Doctor0, fresh webpack/Turbopack와 Chromium27/Firefox27 모두 exit0 | 12b 검증 tree와 merged786 동일; 외부 SSH controller 지연과 제품 test exit 구분 |
| Map | 최종 merged f347, 원 A/B finding closure·source/CI 확인. 이전720의 D286/flake0·runner0·정리 증거 보존 | 사용자 제외 뒤 추가 빌드·운영 수용 미실행, Claude 별도 범위 |
| Weather | 단위308·lint/type/Doctor0·fresh production browser20+tile5, 정확 source CI SUCCESS | 합성 merge tree==검토2b348; CI 실측과 실제 운영 수용 별도 |
| Concierge | 단위396·lint경고0/type/Doctor0·guard·C11 production browser10 PASS | 기존394는 remount 수정 전 체크포인트; 최종396/10과 혼합하지 않음 |
| Manager | backend3726PASS/40SKIP, frontend54·lint/type/Doctor0/build/browser2, 중앙 CI SUCCESS | 기존 systemd frontend 방식; Docker 이미지로 바꾼 것이 아님 |
| Pinvi | web531+core138+marker24, 전체 browser209PASS/기존4SKIP·canvas3·restore2, API2259PASS/9SKIP, mobile Doctor20/20·ReactDoctor0/export PASS | 정확528 web/API/mobile/ETL/central 및 READY Aggregate43099590252 SUCCESS, 원 A/B ownfinding FIXED/신규0 |
| Transport 주 PR181 | 공개164/admin356·lint/type/Doctor0·actual153/263, fresh native 공개4/admin18·별도 Alpine 공개4/admin18 PASS, backend CI1548PASS/2SKIP | source936의 과거 검증. 원래17/1 실패 보존·지도 준비 attachment 단언 보강. 후속 관리자 PR182 실행 결과와 구분 |
| Transport 관리자 후속 [PR182](https://github.com/digitie/kor-travel-transport/pull/182) | reviewed c3da2632101c347a5e4fc288762de635c9c255b5 → merged 6b75c3b3d1e6dec8fc346a847428f15e4f3153b4, tree077e7c14f87aa55fe1774c0a706bcf9f1e3e509c는 검토·CI 합성072c51과 동일. CI43130997296/43130998009 SUCCESS, backend1548PASS/2SKIP/6warnings·공개164/admin432·양쪽 Doctor0/type/lint/build PASS | 원 A/B 입력1 BLOCK 원문 보존 → 입력2 own FIXED/SOURCE PASS·신규0 → 최종 PREMERGE SOURCE+QA PASS·신규0. 당시6b75 ARM image42b·공식 관리자 적용/healthy/current/postproof는 완료했으나 실제 QA는 최종 FAIL이고 후속 strip 검증 대기였다. 이후47a/3f207 및 최종f30/0ac648의 수용과 구분하는 역사다 |
| Transport PR182 native/Alpine 검증 | 각 환경 기존18+리뷰 회귀4+기능 보존6, 합계56PASS·skip/flake/errors0. 공통 파일 각263개·검증 source904개·x64 Alpine image source293개 일치·compiled routes32개 | 검증 이미지/격리 브라우저 결과다. 실제 ARM 운영 이미지나 관리자 정상 인증 수용으로 세지 않음. live-e2e workflow SKIP도 PASS에 합산하지 않음 |

Doctor0과 ESLint 경고0을 동일시하지 않는다. Pinvi 웹의 기존 인증 hard navigation lint 경고1은 별도로 기록되어 있으며 최종 React Doctor 진단은0이다. 테스트 SKIP은 PASS 수에 합산하지 않는다. source 검토·QA를 구현자의 재검토로 대체하지 않았다. 최종 문서 자체는 앱 source 원 A/B 검토와 별도 입력으로 부모에게 인계한다. Common50의 이전307 CI green과48109 입력3의 원 A current 보존 범위 P2 BLOCK·원 B 신규0 PASS는 역사 원문으로 보존한다. 후속4c43은 selected Transport current 갱신과 OTHER 앱 current/공개936 보존을 구분했고, 최종 사실 source37a264b34b0a9ed4189f62a271722dbdc6b8235a는 원 A/B docs5 PASS·신규0 및 정확3CI/9job SUCCESS를 받았다. closure 원문만 추가한 최종 d2d3c295d8dd4700488c8170b77303d03d44d15b는 frontend43233563740·python43233563534·docs43233563636의3workflow/9job 모두 첫 attempt SUCCESS를 확인했다. [PR50](https://github.com/digitie/kor-travel-common/pull/50)은678a5bcf0150ac0386bfa86106e7e0f4f77e8639로 병합되었고 fetched main/검토d2d3의 전체 tree550b152ae33f2b441ca721f51c0b76350d3acf4a가 같다. 이전 검토·CI·병합 대기는 당시 상태로 보존하며 현재 공개 영수증은 위 고정 merged 링크를 따른다.

Pinvi A의 checkout/image provenance 오표기와 B의 dead trigger2개는 같은 불변528 후속 입력에서 각각 원 리뷰어가 직접 FIXED/PASS로 닫았다. source531/209 결과와 API2259 결과를 이전328/527/2258 체크포인트로 대체하지 않는다.

### 7.2 실제 배포와 runtime 수용

| 프로젝트 | 배포 source·산출물 | 실제 수용·상태 |
|---|---|---|
| Manager | merged9910, systemd의 새 frontend build와 공식 SDK 설치 | 실제 로그인/보호API/VirtualTable/Pretendard/모바일/logout PASS. WebSocket 상태·로그 positive control 및 logout후30초 재연결0. 완료1 |
| Concierge | mergedf2db, 새 UI image `sha256:77de763323a8b08881d1b5398c64533940c31a7ab68c0449fc569dba9621bc1c` | 공식4서비스 활성화 완료. 원 A 실제 로그인1/로그아웃1·보호401→200→401·지도 worker1/VWorld34건200·표/키보드·Pretendard·375/1280 PASS. 완료2 |
| Pinvi | mergeddd3, 새 web image `sha256:a029e906dfd0ae534c75bf638e3af292e9fa6a3dfc4357e79e0640696f0bcb6e` | 공식 pinned receipt committed0·binding/G해제·actual297파일 일치. 실제 로그인1/logout1·보호200→401/이전쿠키401·지도15건200·표/폰트/반응형 PASS. 완료3 |
| Weather | mergedfaca, arm64 image `sha256:e8abd9f4af7ff79fff64d869bd4d98338143cb17d9fbe874556abfabaa9f7d7b` | SDK590 공식 dry-run/confirm/current0. 실제 로그인1/logout1·보호401→200→401·지도40건200·VirtualTable/overlay Escape·focus return·폰트/반응형 PASS. 완료4 |
| Geo | merged786, arm64 image `sha256:82c7c354dd2fb3af1c54f70e42abaf5b42c0e31c8aa2b74cde937e5cdd8b11c7` | 공식 dry-run/confirm/current/verify0·healthy·환경 전체 보존·비선택54개 불변. 실제 로그인200/보호200·공통 표37행·검색/모바일/Pretendard·지오코딩200/후보1·canvas/marker/VWorld9건200·logout200/보호401·page error0·도메인 쓰기0. 완료5 |
| Transport | 공개 merged936·arm64 image `sha256:32626dee05553b1d448232b9716c541a3af4f4b55255b016246737f4bfcc545d`; 현재 관리자 PR186 mergedf30dbd82·ARM image `sha256:0ac648f860f7aba501ad6ff1b6f4457344e0ed91ebd60a2d1a9a4338b97be69b` | 공개 단계별13/13 수용 유지. SDK508 공식 적용·부모 원격44검산·새 정상 단일 세션9/9 PASS·실제PNG2+2 decode/zoom/메뉴/폰트/cleanup 확인. UX5/total60의 새 계약 PASS이며 이전 M9 5초 실패2건은 역사로 보존. owner freeze63 검산 완료·Common50 merged678a의 공개 영수증 연결 |
| Map | 주 PR1496 mergedf347 이력 보존 | 사용자 제외. Claude가 PR1493 뒤 별도 빌드 담당; 이 통합의 미완 배포로 집계하지 않음 |

Geo의 최종 actual UI driver는 exit0/status PASS이며 실제 활성 이미지와 대표 기능을 확인했다. 앞선 하네스3시도는 보존한다. 첫 시도는 Playwright 경로 누락으로 브라우저를 시작하지 못했고, 두 시도는 응답 status 접근 helper 오류로 정상 로그인·정리를 수행한 뒤 실패했다. 하네스만 수정했으며 제품 소스 변경이나 이미지 재빌드는 없었다. Transport의 검증용 native/Alpine 이미지는 운영 배포로 세지 않는다. 직전 범위에서 배포·실제 수용을 확인한 프로젝트는6개다. Transport 공개 단계별13/13과 당시 관리자 strip47a/3f207의9검사·최종 정리를 확인한 수치이며, 이후 추가된 Geo형 Drawer·PC 세로 rail 메뉴 요구의 완료를 뜻하지 않는다. Map은 사용자 제외로 완료 수에 넣지 않는다.

Transport 공개936은 같은 실제 image3262의 단계별 브라우저 증거를 감사해 수용 항목13/13을 충족했다. 홈페이지의 실제 데이터·공통 표·Pretendard, calendar Escape/초점 복귀, 분석4탭, 요금 입력 연결, 375px 실제 카드·폰트·가로 넘침0을 확인했다. KST 날짜/공항 컨트롤로 ICN의1009행/946관측·차트·요약3개를 확인했고 CJJ/GMP의 실제 GET200/0행은 정상 empty로 남겼다. 데이터 주입이나 관측값으로의 억지 변환은 없었다. 원 하네스 실패·후속 성공과9개 세션/정리 증거를 모두 보존했다. 이13항목의 단계별 수용은 single-run PASS나 aggregate suite 실행이 아니다.

Transport 관리자는 실제 mergedM6b75의 ARM image42b를 SDK508로 admin-only dry-run1/confirm1 적용했고 healthy/current/postproof를 확인했다. 비선택54개 변화0, backend499/schema0042·공개936/image3262·인증/세션 환경을 보존하고 승인된 releaseSHA만 바꿨다. 정상 UI 로그인1회200·보호 releaseM·공통 표·Pretendard·Popover·주차장 상세·저장 metro417행·일반철도 workbench/공식·전화·주소 동작까지 actual run1에서 통과했다.

다만 같은 run1의 actual-map-tiles는 **FAIL**이다. 지도 응답76건에서 HTTP 오류는0이지만 validImage200이0이었고, 해당 원문은 보존한다. run1 실패 뒤 logout cleanup303·브라우저 종료를 확인했고 당시 five-widths·zoom·최종 보호 API401은 NOT_RUN이었다. 이후 그 당시M6b75/image42b의 실제 QA를 마쳤으나 최종도 **FAIL**이다. 지도 응답36건은 key locator 관련 XML이며, 네 viewport는 통과했지만768px은 하네스 실패로 남았다. zoom과 logout303→보호401은 후속 검사에서 통과했다. 이 서로 다른 실행 결과를 한 번의 전체 PASS로 합치지 않는다. 이전 M6b75/42b의 QA 시점에는 Transport 전체/여섯 번째 앱 수용이 미완료였다. 이후 새 M47a/3f207의 성공과 이 실패 이력은 구분한다.

Manager SDK 후속 [589](https://github.com/digitie/kor-travel-docker-manager/pull/589)·[590](https://github.com/digitie/kor-travel-docker-manager/pull/590)은 별도 원 A/B·CI 뒤 병합되었다. 당시 SDK590 ca1d32b05f7a8418708bdd4f84449d79df57a102는 두 호스트에 설치·소스/config82 및 wheel Python71 대조를 완료했다. N150은991→ca1 직접 설치1회·정식 execution rebind 후 pin verify0/current/rotation idle, 보호24개 변화0이다. 다른 호스트는 보호55개 변화0이며 기존 pin 부재의 verify2를 PASS0으로 바꾸거나 임의 bootstrap하지 않았다. 이 업그레이드의 frontend rebuild/restart는0이다. 새 공통 제공 비밀번호가 Manager 두 호스트 offline 값과 맞지 않아 새 online 로그인은0회로 남겼으며, 앞선991 실제 로그인 수용과 구분한다. 계정 변경은 없다.

Transport 공개·관리자 배포를 위한 후속 [SDK591](https://github.com/digitie/kor-travel-docker-manager/pull/591)은 reviewed e533820112372fb2f23982265b7a9575db7a0431에서 merged508b074cff137e5cca79318f4f99ec7d385e655b로 병합되었다. 원 A/B PASS·정확 CI3979PASS/40SKIP·frontend54/browser2·policy SUCCESS 및 tree98f2fefd9349dc0538ca8cd5b4e250ab84b2dc77 동일성 뒤, 양 호스트 설치 VERIFIED를 확인했다. 호스트별 source/config82·wheel Python71 일치, 보호 컨테이너55/23개 변화0, root 환경·pin/current 보존, frontend rebuild/restart0이다. N150의 정식 rebind 뒤 pin verify0/current/rotation idle, 다른 호스트의 기존 pin 부재 verify2/bootstrap0도 구분한다. SDK 설치 당시 앱 적용은0이었고 이후 Transport 공개 적용은 별도 receipt로 확인했다.

기존478의 PUBLIC ONLY 결과는 combined 승인으로 전용하지 않는다. 관리자 후속 경로는 기존 transport.admin/G/frozen/current·admin-web 단독 선택 계약을 유지하고 backend499·DB0042를 동기화·마이그레이션하지 않는다. source936 관리자에는 운영 기능 누락이 있어 적용하지 않았다. 운영 route manifest에서 확인한 두 경로와 독립 기능을 보존한 PR182는 merged6b75로 확정되었고 실제 ARM image42b를 공식 적용했다. 해당 배포와 실제 QA의 최종 FAIL은 역사로 보존한다. 이전 baked 지도 키 동일성은 당시 미입증이었으며, 사용자 추가 승인으로 Geo에서 실사용 웹 키를 확인해 Transport 한정 반영을 준비한다. Geo 운영 소스는 변경하지 않는다. 승인된 Transport 웹 키 등록 입력은 이후1회 갱신되었지만, 실제 운영 이미지·새 키 브라우저 수용은 아직 이전 상태다. 새 UI 이미지·재배포와 새 수용은 각 실제 증거로 별도 확인해야 한다. 주 PR181 기준412개 의존성 행과 C11 산출물은 후속 PR182에서도 package/lock/vendor 변경 없이 유지된다. 새 이미지의 실제 HTTP404를 측정한 것으로도 표시하지 않는다.

기존 공식 Manager 경로를 사용하고 G·pin·canonical current/receipt를 우회하지 않았다. Pinvi paired 배포는 app 소유 API/code/web 및 기존 Map pin 재구축을 포함하지만 Map source fd1·DB/schema identity를 보존했다. Concierge는 app 소유4서비스를 공식 활성화했고 non-UI source/image·환경과 비대상 수명주기를 확인했다. PG/RustFS/global Dagster를 임의 재시작하거나 새 migration을 적용하지 않았다.

Manager991 설치 관찰에서 공유 PostgreSQL의 aggregate configuration digest 차이1건은 별도 관찰로 보존한다. ID/image/start/restart 수명주기는 같았으나 원시 before 필드가 없어 변경 원인을 확정할 수 없었다. 이를 전체 configuration 불변이라고 과장하거나 임의 복구하지 않았다. 이후 SDK590의 자체 fresh baseline 보호 비교는 별도 증거다.

사용자 최우선 모바일 메뉴 대조에서 정본 RW9/UX G1.2의 strip DEFAULT와 Geo drawer OPTION 허용을 확인했다. 이는 실제6개 앱 UI가 모두 동일하다는 관찰이 아니며, Transport의 메뉴 정합성 수정이 별도로 필요했다. 최종 strip 소스 `b043c0d8a57df5ea4ec7de780551dff7ea171dc0`(tree `fc4c8854fe0f6f046ea6e2997edea2aa5903ab17`)의 [PR183](https://github.com/digitie/kor-travel-transport/pull/183)이 실제 Draft로 생성되었다. 변경6파일은 shell TSX/CSS·unit·새 E2E·문서2개이며 C11/package lock/vendor/backend/auth/schema는 그대로다. 정확 b043 checkpoint에서 focused24·전체 관리자435·type/lint·Doctor0·installed/external 검사7개 exit0을 확인했다. 이 수치는 b043의 체크포인트이며 아래 후속 실패/수정을 포함한 최종 통과로 전용하지 않는다. 이전 drawer 초안과도 별도 소스의 결과다.

PR183의 b043 원 A/B 입력1 판정은 각각 P2 1건 BLOCK이며 그 원문은 보존한다. 후속 db58에서는 양측 own finding을 FIXED로 닫고 source PASS·신규0을 확인했으나, unit451·lint/Doctor0·guard PASS 뒤 타입 검사에서 Page.route 대역의 Disposable mock 계약과 관련된 TS2345가 실패했다. source 판정과 실행 gate를 구분하며, 이 단계의 native browser/Alpine은 NOT_RUN이었다.

ee45a482eeabd33c448c8061d9a3ea3b400705b6은 typed mock과 문서의 최소 delta이며 local451·Doctor0·native39/Alpine39 PASS 원시 로그를 확인했다. 해당 formal receipt는 담당자 정리 중이며, 이 결과를 아래 새 cd4 소스의 통과로 전용하지 않는다. 이후 실제 screenshot에서 비지도 화면 header stretch를 발견했다. 이전 BLOCK·TS2345 및 모든 하네스 실패는 후속 성공으로 소급 변경하지 않는다.

Mendel의 격리 ee45 native/CSS 단일 override 대조는375/768/1023px에서 진행했다. 768px 폭에서 viewport 높이900→1100px일 때 기존 rail 높이는282.75→382.75px로 늘었지만, override 뒤171→171px·중심 정렬을 확인했다. 이 대조는 새 install/build·운영 변경이 없는 격리 실행이며 정식 새 소스 전체 회귀를 대신하지 않는다.

PR183 최종 검토 소스는 `cd4ff768894d29199674c9f540399f7aeaf65170`이다. 모바일 모든 페이지의 grid rows를 `auto minmax(0, 1fr)`로 명시하고 기존 비지도 case에 높이 불변 assertion·문서를 반영한4경로 변경이며 제품 JavaScript는 바꾸지 않았다. 원 A/B source4와 execution5는 모두 frontend PASS·신규0이다. 정확 cd4의 native39+Alpine39=78PASS·skip/flake/errors0, 공통 파일 각263·전체 source907·x64 builder COPY 입력296개 일치와 native compiled routes32개를 확인했다. 최종 정확 CI는 frontend/admin·정책과 backend까지 SUCCESS다. backend1548PASS/기존2SKIP/6warnings·50분47초이며 live-e2e SKIP은 PASS로 세지 않는다. 이후 PR183을 `47a4719ab772f7d0e7a707df2ed6a6d08b1cc4ea`로 병합했고 전체 tree `510888aa00fa949531e392c68061ff9ee72a5b83`가 reviewed cd4와 같다. 이 source/CI 증거는 정상 운영 수용을 대신하지 않는다.

cd4의 최초 unit worker 실행은61파일/434PASS 뒤 error1·미수집17개로 실패했다. 설정·제품 소스·assertion·pool·timeout 변경 없이 대상17개를 한 번, 전체62파일451개를 한 번 재실행해 각각 exit0으로 복구했다. 최초 실패/status/log는 보존하며 자원 원인을 확정하지 않는다. raw PASS·재실행 이력·formal receipt를 구분한다.

fresh 실제 cd4 코드/CSS의375·768px에서 rail171/171px, logo/logout 중심 차이0, active 차이0/−0.5px 및 Pretendard custom glyph 각6개를 확인했다. 768px에서 viewport 높이900→1100px의 rail 변화0이며 부모의 실제 화면 확인도 기록했다. CSS 주입으로 통과시킨 결과가 아니다. 격리 검증 종료 당시 운영 관리자는 M6b75/image42b였고 이 상태의 FAIL 증거를 보존했다. 최종 merged47의 실제 ARM 이미지 `sha256:3f2073a3768bc90f07f4ff3ef614c9ceb263fb66b8b63ce125afeead1a58fb09`를 정상 docker build로 생성했다. 같은 tree의 builder cache를 재사용한4.3초 빌드이며 기존 이미지를 retag한 것이 아니다. 공통263/source907/COPY296/routes32와 승인된 Geo 키의 compiled 일치3곳을 확인했다. private collector가 처음 변수명을 shadow한 실패는 보존했고, NODE_AUDIT·strict predicate를 바꾸지 않은 채 별도 web_key 변수로 교정해 같은 이미지가 PASS했다. 부모가 파일18개와 strict proof6개의 hash를 검산했다. 이는 공식 적용 전 이미지 검증 증거이며, 그 뒤 아래와 같이 같은 새 이미지의 공식 적용·정상 QA를 수행했다.

이 문단은 strip 검증 당시의 이력이다. 앞선 Geo형 drawer 초안의24unit/type/lint/Doctor0/build/10browser PASS는 별도 초안 증거이며, 후속 strip b043/db58/ee45/당시 cd4의 통과로 전용하지 않는다. 그때 새 UI와 승인된 지도 키 반영은 별도 소스·이미지 검증 대상이었고 M6b75/42b의 증거를 새 수용으로 소급하지 않았다. 당시에는 새 strip/지도·인증·반응형 수용 전 Common/Geo 최종 정산을 대기했다. 이후 f30/0ac648의 새 계약9PASS·최종 freeze와 Common50 병합678a·공개 영수증 연결이 완료되었다. 당시의 발행 대기와 현재 문서의 원 A/B·정확 CI gate를 구분한다.

지도 키 선택도 실제 운영 소스를 대조했다. Geo는 KTG_VWORLD_API_KEY가 NEXT_PUBLIC fallback보다 우선하며, 잘못된 공유 public alias와 실제 선택된 KTG 키는 달랐다. 사용자 승인에 따라 실제 Geo 환경·이미지 소스/provenance를 확인했고 Transport origin으로 제한된 GET2회에서 유효 PNG200을 각각 확인했다. 이는 **키·origin 조합의 제한된 입력 검증이며 새 UI 이미지나 실서비스 브라우저 수용은 아니다**. 이후 승인된 등록 Transport 운영 입력의 웹 키 한 필드를1회 갱신했다. natural/scoped config가 검증된 키를 선택하고 다른 bytes·parsed 필드·uid/gid/mode는 같으며, 이전 입력은 root0600 backup으로 보존했다. 55개 runtime 변화0, root Manager/Geo/Map/backend/auth/pin/current 변경0이다. 등록 입력 뒤 최종 ARM image3f207에 승인된 키가 컴파일된 것은 확인했다. 입력/이미지 검증 시점에는 이전 M6b75/image42b·새 키 브라우저 수용0이었다. 이후 새 M47a/image3f207를 적용해 실제 PNG·decode·카메라 검사를 통과했으며, 그 결과를 앞선 제한된2회 GET proof와 구분한다. Geo 운영 소스·환경·pin/current/image와 계정은 바꾸지 않았고 키 값·키 URL·운영 호스트·private 파일 경로는 출판하지 않는다.

새 Transport 관리자 merged47a4719a/image3f207는 SDK508의 admin-only dry-run1/confirm1과 current/postproof를 통과했고 비선택54개는 그대로다. 선택된 Transport 관리자 current는 새47a/image3f207로 정상 갱신되었다. 보존한 범위는 다른54개 서비스·공개936·backend499·root/auth/pin 및 타 앱 current이며, 선택된 관리자 current까지 불변이었다는 뜻이 아니다. 부모가 frozen37개 member의 hash 불일치0을 검산했다. 실제 정상 QA 관찰은9검사 PASS/실패0·로그인1회/로그아웃1회·최종 보호401·실제 Pretendard이며, 폭320/375/414/768/1023/1024/1280과 breakpoint 왕복·높이 변화0·scroll280에서 초점 보존을 확인했다.

지도 문제는 이 새 이미지의 실제 브라우저에서 해결을 확인했다. 초기 구간의36개 PNG는 모두200·PNG signature/IHDR256이었고 카메라 이동 전16/후20을 관찰했다. 실제 image decode는 전후2개씩, 총4개를 검사했고 zoom7→8을 확인했다. 최종 누적 관찰은 응답96개/유효 image200 68개/HTTP 실패0이다. **96개 전체를 decode했거나 모두 유효 이미지였다고 표시하지 않는다.** 최종 QA 영수증에서9검사 PASS/실패0, 정상 로그인1/로그아웃1·보호401, 브라우저 종료·PID 부재·소유 포트0·heavy0을 확인했다. 부모는 frozen13개/source26 hash 비교와 참조5개를 검산해 불일치0으로 수용했다. 따라서 당시 범위의 Transport를6번째 수용 앱으로 집계할 수 있다. 이47a/3f207의9PASS는 불변 역사이며 최신 Geo형 메뉴의 증거로 전용하지 않는다. 문서 담당자가 추가 runtime QA를 실행하지 않는다. 이후 새 Drawer/PC rail 메뉴는 f30/0ac648에서 새 계약의 정상9PASS를 확인했다. 그 뒤 owner 최종 freeze63 검산과 Common50 병합678a가 완료되었다. 이 문서의 최신 사실 delta는 별도 원 A/B·정확 CI 검토 대상이다.

최신 사용자 명시 선택은 “메뉴 형태를 다시 Geo와 동일하게, PC에서는 세로 메뉴”다. 이전 RW9/UX G1.2 strip DEFAULT와 Geo drawer OPTION 비교 및 strip 수용은 당시 결정과 증거로 보존한다. 이 사용자 선택인 **Geo-equivalent 모바일 Drawer + PC vertical rail**은 부모가 구현해 최종f30/0ac648의 실제 수용까지 확인했다. 이전 strip47a/image3f207를 새 메뉴의 완료 버전으로 부르지 않는다. 현재 확정된 source f30/image0ac648의 실제 수용 증거를 따르며, 실제 Geo UI·운영 소스를 수정하지 않는다.

이후 Geo형 메뉴의 [PR184](https://github.com/digitie/kor-travel-transport/pull/184)가 merged `88566f7d16c3bb1b497d3ce0c4869c43d6d51844`(tree `00b6474f7d9d6b39bcd5a633a392dfa23d202392`)로 확정되었다. PC16rem/4rem 세로 rail과 모바일 left Drawer(18.5rem/88vw)의 Native41·Alpine41, 원 A/B SOURCE3/EXEC4/CI CLOSE5 PREMERGE PASS·신규0 및 정확 main43170676902/policy43170677221 SUCCESS를 확인했다. backend1548PASS/기존2SKIP/6warnings·공개164/admin452이며, 첫 Native private1FAIL의 원인 미확정 기록은 보존한다. **이 source 검증 시점에는 실제885 ARM 이미지·운영 적용·actual QA가 NOT_RUN이었다. 이후 image5ffe의 공식 적용과 첫8PASS/1FAIL은 아래 별도 증거로 연결하며, 새 Geo형 메뉴 전체 수용 완료로 표시하지 않는다.** 해당 PR184 검증 시점에는 Common50·Geo 최종 발행 HOLD였다. 이후 PR185/186과 Common50 병합 결과는 아래 최종 증거로 구분한다.

그 뒤 실제 Geo형 메뉴 M88566f7d/image5ffe49를 SDK508로 dry-run1/confirm1·healthy/current/postproof 적용했고 부모가 원격38개 hash를 검산했다. 정상 첫 단일 세션은 **8PASS/1FAIL**이며31개 frozen 원문을 보존했다. 메뉴는 실제9개 폭/11행·Pretendard11표본·높이 불변을 통과했고, 지도는 bounded PNG40개(이동 전20/후20)·실제 decode2+2·zoom7→8, 표/업무·Popover·정상 logout 후 보호401을 확인했다. PC/375/768 메뉴 실제 PNG3장도 부모가 직접 확인했다.

별도 연락처 검사는 철도역 지도 region visible 선행조건에서 실패해 href assertion에 도달하지 못했다. 원인을 확정하지 않고9PASS·단일 clean 수용·현재 Transport 전체 완료로 부르지 않는다. 이전 운영M885의 이 target FAIL은 보존한다. 이후 M9에서 해당 연락처 검사는 PASS지만 별도의 새 PNG target 실패가 있어 정상 전체 수용과 구분한다.

후속 [PR185](https://github.com/digitie/kor-travel-transport/pull/185)의 최초 검토 소스는 `bf937d1cb79b06c8da2ffb8c24b42e8c527f5995`였다. GeneralRailGuide의 불필요한 ssr:false를 제거하고 기존 TransportMap을 static import하도록 바꿨다. 새 SSR 회귀2개는 old RED/new Native+Alpine GREEN이다. 원 A/B SOURCE1 제한 검토는 PASS·신규0이었으나 당시 실행 gate는 Native43 clean/Alpine42PASS·1FAIL이었다. 이 실패와 운영M885의 첫 target FAIL/원인 미확정은 보존한다.

bf9 첫 collector의 대상 실행은0회였지만, 이후 원래375px1case를 본 bounded 관찰은 **총2회**다. worker R2는 target1 PASS 뒤 detail1034ms→departure1179ms를 관찰했다. 부모가 이 결과를 인수 전에 받지 못해 별도 target1을 중복 관찰했고, 그때도 PASS 뒤 detail967ms→departure1161ms로 focus가 옮겨갔다. 양 원문과 worker frozen16개를 보존·검산했으며 두 진단의 운영 로그인은0회, 다른42case 반복은 없었다. 최초 Alpine의 원 실패는 원인 미확정 FAIL로 그대로 남고, 순간 assertion PASS2건으로 재판정하지 않는다.

후속 소스는 passive initialDepartureName의 revision을1→0으로 분리하고 explicit intent/reassign 동작은 바꾸지 않았다. 실제 CommonPicker의 지연 catalog/remount 회귀5개는 before2FAIL/3PASS→after5PASS였다. 짧은 assertion의 PASS를 후속 focus 불변까지 증명한 것으로 소급하지 않는다. 이 관찰 횟수 정정은 새로운 edb Native43/Alpine43의 첫86PASS 결과에 영향을 주지 않는다.

PR185 최종 검토 소스는 `edb6538209d5fc2d1b64e001af971dfc0e82ea55`이며, 실제 merged source는 `9aebd19947c3606c2953eb564e7eee4541be5856`이다. reviewed edb·CI 합성4d9·merged9aeb·origin/main의 전체 tree가 모두 `7ffb15929c7b8de0e48555312797fc66aa47ed58`로 일치한다. 이4-way bridge SHA256은 `063e8e1b33d931156f7abd8072a100554a54bf38c2d0d8c3c4c6968486df2a57`이다. 원 A/B SOURCE2 모두 PASS·신규0, local458unit/type/lint/Doctor0/guards·Native43/Alpine43 각각 clean PASS이며 retry/skip/flaky0의 원시 stats를 확인했다. source909/COPY298/Common263/routes32를 대조했고 full QA 최종 영수증은 부모의100개 검산으로 확인했다. 정확 CI43195806562와 policy43195808014는 모두 SUCCESS다. admin458/public164·type/lint/build/Doctor0, backend1548PASS/기존2SKIP/6warnings·1857.39초를 확인했으며 live-e2e SKIPPED는 PASS에 합산하지 않는다. 원 A/B SOURCE2/EXEC3/CI4 모두 PREMERGE PASS·신규0이고 부모가 전체 원문을 확인했다. ARM 후보 d85f의16개 local/remote hash strict PASS는 당시 apply-ready 증거가 아니었다. 이후 실제 merged9aeb 정상 build/audit로 imagecb611을 확정하고 공식 적용했다. **당시M9 첫 actual9는8PASS/1FAIL로 수용 미완료**였고, 후속 f30의 새 계약 PASS는 별도 증거다. 기존 source PASS·격리 실행 또는 운영M885의8PASS를 새 정상 수용으로 전용하지 않는다.

이전 운영은 merged9aebd19947c3606c2953eb564e7eee4541be5856/imagecb611f30이었으며 그 배포·QA 증거를 보존한다. SDK508 공식 dry-run1/confirm1·Errors0·healthy/current/postproof를 완료했고, 선택된 Transport 관리자 current를 이 새 tuple로 갱신했다. 타54개·공개936/image3262·backend499/schema0042·root/auth 환경·pin 및 타 앱 current는 보존했다. 부모가 원격42개 원문의 SHA/bytes/mode를 검증했고 로컬 보관은 그중15개 subset이다. freeze harness의 출력 schema 오류1회는 원문을 보존해 교정했으며 SDK apply를 재시도하지 않았다.

M9의 첫 정상 전체9검사는 **8PASS/1FAIL**이다. 이전M885에서 실패했던 연락처 검사는 Guide200/65개·공식/tel/address-map 동작까지 PASS했다. 메뉴 실제9폭/11행·메뉴 Pretendard11표본·표와metro417행·업무/Popover·logout 후401 등8검사는 통과했다. 새 실패는 actual-png.cjs의 첫 canvas toBeVisible5000ms(13:140)이며 decode·zoom 전이므로 actualPNG=null/tilemetadata=[]다. 전체 관찰자의72응답 중45개는 signature/size-qualified image200·HTTP 실패0이지만 **45개를 실제 decode한 것은 아니다**. 원인은 미확정이고 source도 바꾸지 않았다. 정상 로그인1/로그아웃1·브라우저 종료·cleanup0의 최초 결과는 유지한다.

당시 부모가 승인한 다음 실행은 Mendel의 PNG-only target1 bounded 진단 정상 세션뿐이었다. 그 진단도 기존5초 조건에서 FAIL했으며 통과한8개나 전체9를 다시 실행한 것으로 기록하지 않는다. 이 이전M9의 결과를 후속 f30 새 계약의 단일9PASS로 소급하지 않는다. 이 당시에는 Common/Geo 발행 HOLD였으며, 문서 담당자는 별도 runtime QA를 추가 실행하지 않았다.

최종 후속 [PR186](https://github.com/digitie/kor-travel-transport/pull/186)은 mergedf30/sourcebd08/CI8303의 동일 tree4fec로 병합되었다. 앱 loader p 전용 표시 수정과 No-JS/문서 검증, 원 두 Source2/helper3/final EXEC4 PASS·문서P3 수정 및3CI SUCCESS를 마쳤다. 실제 정상M ARM image0ac648의 strict909/298/263/32·OCI/default M·승인 입력 확인 뒤 공식508 dry-run1/confirm1을 적용했다. 부모는 원격44개 원문을 검산했고 새 정상1로그인/1로그아웃의9검사가 모두 PASS였다.

현재의 실제 PNG decode2+2/zoom7→8·UXfeedback2.808995초/bootstrap5.644271초·own loader0은 새 UX5/total60 계약의 관찰이다. 원 early-canvas5초 FAIL2건과 형식 검사 관찰45/19건은 계속 실패/관찰로 남기며 성능 개선이나 이전 조건 통과로 재해석하지 않는다. 각 source·계약·이미지·세션의 증거를 구분한다. PNG cleanup·browser close·node exit0·owner 최종 영수증과63개 frozen index·부모 검산을 완료했다. 새 정상 세션은 추가 세션/target/retry0으로 동결되었고 그 뒤 Common50 병합678a와 공개 영수증 연결도 완료했다. 추가 runtime QA 없이 단일 MD 최종 사실 delta를 원 A/B·정확 CI에 인계한다.

### 7.3 증거와 완료 조건

공개 소스·CI 링크는 각 주 PR과 정확 merged package 경로를 따른다. 상세 runtime 영수증은 부모의 비공개 통합 감사 보관소에 유지하며 접속값·credential 파일·쿠키·키 URL·로그인 요청 본문을 이 문서에 넣지 않는다.

| 증거 | 확정 내용 |
|---|---|
| [공개6개 앱 배포 영수증](https://github.com/digitie/kor-travel-common/blob/678a5bcf0150ac0386bfa86106e7e0f4f77e8639/docs/reviews/adversarial/evidence/2026-11-12-frontend-deployment-receipt.json) | Common merged678a5bcf의 공개 JSON SHA256 `e45a1119e52e89b6d39eab3d689fc39ed9e7a482ac4f7d55f70b468df30b833e`. 최종6개 실제 수용·Transport 공개/관리자 분리·이전 실패/진단/계약·입력63개 검산·원본 SHA를 연결 |
| Pinvi final-deployment-acceptance-manifest.json | SHA256 `b36cc4e2d9aa77056dd6dbbce3fce2d6a70a5c3820168e8da117898e2f644c88`, 공식 receipt·binding·actual297·실제 UI·정리 등14파일 해시 |
| Concierge 원 A acceptance.json | SHA256 `bfe23ea74f931cf5999eb7c04ea1a361ae6f717cda5bf5a818e99c74b090ff48`, 이미지 유지·실제 UI 수용·own cleanup |
| Weather weather-final-deployment-acceptance-manifest.json | mergedfaca·실제 image·SDKca1·공식 활성화·40건200·정리와 원문 파일 해시 |
| Manager production-completion-receipt.json·590/591-two-host-sdk-completion.json | frontend991 실제 수용·별도 drift 관찰·SDK590 이력과 양 호스트 SDK508 설치 VERIFIED를 구분. SDK591 원장 SHA256 `bed584db7a8a6fea80b03ada4d940fc142347abf68673297671fb7e314edf4c5` |
| Geo final-deployment-acceptance-manifest.json | SHA256 `49170c6b3365032c13f829a8e60e2e16cf859967d8840ac696b455367a882258`, 공식 dry-run/confirm/current/verify0·실제 image82c7·환경 전체/비선택54개 보존·최종 driver0/status PASS |
| Transport 공개 public-aggregate-acceptance.json | SHA256 `4482143fa58847ff13704d1f8e1f488730ce570ce8ee617f8d13e90fcedfedc6`, source936/image3262·실제 단계별13/13, singleRunPass=false·aggregateSuiteRun=false. public-final-acceptance-handoff.json과 연결 |
| Transport transport-pr182-merge-and-tree-receipt-20261112.json | SHA256 `bee3fb6261be8fda0b1fb0b17b562298626f5444c80d183147b52c81eeee5208`, merged6b75/tree077e·CI 둘 SUCCESS·원 A/B 최종 PREMERGE SOURCE+QA PASS·신규0 |
| Transport 관리자 c3 handoff-manifest.json | SHA256 `5de3d250e99aad051e122056fbca98607adc6720bd24bdfefa9daaf23d65c0c7`, source432unit/Doctor0·native/Alpine56PASS·공통각263/source904/검증 image source293/routes32 및 원문 해시 연결. 정상 운영 수용은 별도 |
| 이전 Transport 관리자 M6b75 official final-receipt.json | SHA256 `50462d50110f37e76bc46cbd0fea6d1107b240b6bf0d2c912c548fa348596ff9`, 실제M6b75/image42b·SDK508 admin-only dry-run1/confirm1·healthy/current/postproof·비선택54개 및 기존 backend/schema/public/auth 환경 보존 |
| Transport 관리자 actual run1 admin-official-fresh-acceptance.json | SHA256 `ea52001f5130a951fbc82dcb602352def3ae18794e55e04941697dae4ce1ba12`, 실제 로그인/보호/표·폰트/도메인 기능 부분 PASS, 지도 타일 validImage0으로 FAIL. cleanup303/browser closed, five-widths/zoom/최종 protected401 NOT_RUN. 원문 run1의 역사다. 당시6b75의 실제 QA는 최종 FAIL·수용 PENDING이었으며, 이후 새47a/3f207의 최종 수용 완료는 별도 영수증으로 확인한다 |
| library-status-merged-declarations-20261112.json | SHA256 `849c1d78c226bfc66d58e5b39790aabf70bb41ac4993b17004511b911d066026`, 등록65종·10개 표면의 exact registry 선언303개 불일치0, file artifact 참조49개. 선언 대조이며 bytes 검증은 기존 별도 증거에 연결 |
| 최종 M30 owner 영수증·63개 index·부모 검산 | owner SHA256 `da70de7864e05c85b51525bbb568f08a568196a3e99c03414febe9048310b250`, index SHA256 `fd706a8535323f6ebaf63f9cf45d6ab5ebda71ffda9b66c7e0c01ca54732236d`, 부모 검산 SHA256 `1897961b145b8ed289a2c19c2aaaab823de0df7b98cac3cd813f7982c11dc2f1`.63 member SHA/bytes/mode 불일치0·정상1/1·9PASS·node exit0·watchdog 만료0·추가 세션0 |
| PR186 final closure archive | SHA256 `105d6b083da094b32b822fdee59e49fe00b3195816a7026fe30eda672c4d8089`,48 member/46 input의 최종 원문·closure 보존. 이전5초 실패/진단과 새UX5/total60의 검증을 분리하며 과거 verdict를 덮지 않음 |
| 최종 PR186 f30 parent-actual9-and-visual-verification.json | SHA256 `1ad91d29904da6b3583672b4628bc8f2fb04d2846effcfd751b063525f8fbfe0`, raw actual result SHA256 `bbdcf2893eaf894d963f59207f025219eb090b627678d18e3b00d80d2d534a63`. 새M 정상9/9·실제PNG2+2 decode/zoom·폰트12표본/메뉴11전환·PNGcleanup·부모 지도1/메뉴3 실제 view. 이전5초 FAIL2를 재판정하지 않음 |
| 이전 PR185/M9 공식 final-receipt.json | SHA256 `0d0c6ec7773fffda2df69cd9c1f54fb1b68ddb73a14f518ca40333a979b084fb`, 실제9aeb/imagecb611·SDK508 dry-run1/confirm1·current/postproof·타54 보존. 부모 원격42개 SHA/bytes/mode 검증, 로컬15 subset·freeze harness 오류 역사 보존 |
| M9 첫 정상9검사 final-receipt.json | SHA256 `96b8278432c2cb599705d41d26bcba8db836c82d5c0f0f0dba20d237a2148cf1`,8PASS/1FAIL·연락처 PASS/새 PNG canvas target FAIL·actualPNG null/decode전·72관찰/45형식크기검사image200(45decoded 아님)·auth1/1·cleanup0. 최초 결과 동결 |
| PR184 historical closure archive | SHA256 `04d0d1e448b396fdb28f1481f4d9c358c7ec0bf4c766f1285c100b35e451e05f`, frozen36 member의 이전 source/QA/partial runtime 이력. 운영885의8PASS/1FAIL을 정상 전체 PASS로 바꾸지 않음 |
| bf9 focus-observation-count-addendum.json | SHA256 `3ff54061d6ba60c6bced1e3b6db37c602e50c8b06db0001ae7296fed739dae77`, 첫 collector 대상0회·worker target1+부모 target1=bounded 관찰 총2회. 두 순간 PASS/늦은 focus 이동·운영 로그인0·원 실패 보존, edb86PASS와 별개 |
| Geo 실사용 웹 키 선택 final-facts.json | SHA256 `7dd4e1d08c777648481a8364cc00a69dda06ee0c3c41315c20dba6399787c143`, 실제 source/provenance·키 선택 우선순위·Transport origin 유효 PNG200 2회 확인. 당시 제한된 입력 proof이며 이후 image3f207 컴파일 증거와 별도다. 당시 새 실서비스 수용은 미완이었고, 이후 새M 실제 수용 증거와 별도로 유지 |
| Transport cd4 final-manifest.json | SHA256 `c6e8fe89d0d0cfed164a6a2013c8b0a6105133f5e5b2e491a91e1544fef914c6`, native/Alpine78PASS·공통 각263·source907/COPY296/routes32·unit 원실패/17개 대상/전체451 회복·fresh paint·cleanup을 연결. 운영 수용은 별도 |
| Transport merged47 parent-final-image-verification.json | SHA256 `8be1f20421a8297446f073f116a0054bec17ee1dc71467b4b0fc8b84185419be`, 실제 merged source47/ARM image3f207·263/907/296/32·compiled 승인키 검증 및 파일18/strict6 proof. 검증 당시 actualApplyPerformed=false인 적용 전 증거다. 이후 공식 적용·실제 QA는 새 receipt와 별도 |
| 새 Transport 관리자 M47a final-receipt.json | SHA256 `135fa3ba843b000ffad1293870b90202f79fe2bbc4713da4c2939ca415db8ed3`, SDK508 공식 dry-run1/confirm1/current/postproof·비선택54 보존·부모 frozen37 member 불일치0. 이후 actual QA9 PASS·최종 cleanup/fleet 영수증까지 별도 확인 |
| Transport 새M 실제 브라우저 final-receipt.json·parent-actual-qa-verification.json | QA 영수증 SHA256 `e1f61de43e64e33f00aec167485faa86fee7ced82f79f114e44318d2e15ca997`, 부모 검산 SHA256 `51edb7da4e1f3de873438eb50a5d58ff0e56c5587dc55719fb4794dd142b3921`.9PASS/실패0·auth1/1·실제 지도/메뉴/폰트·정리 완료, frozen13/source26 비교/참조5개 불일치0 |
| Geo형 Transport M885 실제 첫 final-receipt.json | SHA256 `5e544d41700cd37aae2ed9e92e60e0237ebc42876db680519688d78aec8e6921`, 단일 정상 세션8PASS/1FAIL·메뉴/지도/인증 부분 성공·연락처 선행 target 실패·31frozen. 전체 정상 수용 PASS가 아니며 원문 보존 |
| 승인된 Transport 웹 키 등록 key-input-receipt.json | SHA256 `a5f904df14c1fee5383829be6be9265db302a4f37369844a10a2927b52d428d1`, 웹 키1필드 갱신1회·나머지 bytes/parsed/권한 보존·runtime55 변화0. 입력 갱신 당시 apply/browser는 미실행이며 이후 새M 적용·실제 PNG/decode 검사를 별도 연결 |

추가 라이브러리 현황 대조는 merged package 선언의 exact registry 대상303개를 확인한 것이다. 아래 전체 직접 의존성의 기준선/최종 합집합412행과 범위가 다르며, file artifact49참조를49개 서로 다른 패키지·설치·이미지로 세지 않는다. 실제 공통 bytes는 불변 C11과 앱별 실제 이미지 감사 영수증으로 별도 증명한다. 이 대조는 npm 최신판 자동 갱신이나 Claude가 별도로 빌드한 Map 이미지 감사가 아니다.

입력1의5개 수용·Transport 대기 문서와 입력2의 CI-LAST 문장 보완은 불변 commit/manifest로 보존했고 원 A/B가 각각 검토했다. 6개 실제 수용·메뉴 정합성 최종 사실은 Common50에서 같은 원 A/B docs5 PASS·정확3CI/9job SUCCESS 뒤 병합678a로 정산했다. 이 문서는 그 공개 영수증에 연결한 제한된 최종 사실 delta를 기존 원 A/B에 인계한다. Geo에는 이 MD 한 파일만 변경하고 리뷰 원문·closure 파일/추가 closure 커밋은 넣지 않는다. raw 리뷰와 불변 입력은 부모 감사 보관소에 유지하고 최종 verdict/SHA는 PR 설명으로 연결한다. 문서 작성자는 새 리뷰어를 시작하거나 자기 PR을 병합하지 않는다. 실제 기기/EAS·Map 별도 작업·확정하지 못한 관찰은 최종 보고에도 그대로 남긴다.

### 7.4 다음 단계 계획과 이번 보고서의 완료 범위

사용자 후속 지시에 따른 **2단계는 계획 상태이며 미실행**이다. 이전 strip 소스의 실제 테스트·배포 수용과 후속 실패는 보존한다. 최신 Geo형 모바일 Drawer·PC 세로 rail 메뉴는 최종f30/0ac648의 새 계약 정상9PASS를 확인했으며 owner 최종 freeze63 검산은 완료했고 Common50 최종 사실 정산·병합678a도 완료되었다. 현재 이 Geo 단일 MD의 원 A/B 최종 사실 검토·정확 CI·병합이 남았다. 후속 빌드 생태계/모든 프로젝트 CI·테스트 규칙 정합성 작업은 아직 미실행이다.

후속 실행 순서는 **Transport 테스트 완료 → Transport Geo형 모바일 Drawer·PC 세로 rail 일치 검증·수정·회귀·새 이미지 실수용(FIRST) → Common/Geo 최종 문서 정산·병합 → Transport 나머지 PR 채택·빌드 생태계 정리 → 모든 프로젝트 빌드·CI·테스트 규칙 정합성 확보 → CI 순서 감사·fail-fast 최적화(VERY LAST)** 이다. CI 순서 감사와 fail-fast 최적화는 앞선 구현·검증·필요한 배포 및 정합성 작업을 마친 맨 마지막에 수행하며, 현재는 미실행이다. 부모가 전체 순서와 소유자를 조정한다.

이전 배포 Transport 관리자 M6b75/image42b의 영수증과 FAIL은 그 당시 소스·이미지의 역사 증거다. 그 뒤 strip47a/image3f207의 정상 수용, Geo형 메뉴885/9a의 실패와 진단을 거쳐 최종f30/0ac648은 별도의 UX5/total60 계약으로 정상9PASS를 확인했다. 각 버전의 증거를 구분한다. 앞으로 새 소스·이미지가 생겨도 기존 증거를 새 버전의 최종 수용으로 소급하지 않고, 필요한 검토·회귀·배포·정상 수용을 별도로 확인한다.

이 단계의 모든 주 PR 병합·공통 bytes 일치가 프로젝트별 빌드/CI/테스트 규칙 전체의 동일성을 뜻하지 않는다. 현재도 Next 번들러·workspace/독립 lock·native/Alpine·Expo export·systemd/이미지 배포 등 서로 다른 실행 경계가 있다. 2단계에서 보존할 제품 계약과 통일할 규칙, 해당 소스·실제 검증·필요한 배포를 별도 확정해야 한다.

공개 영수증의 T-218은 IN_PROGRESS이며 이 보고서로 미완 설계·구현 task를 닫지 않는다. 1단계 보고서가 병합되어도 전체 사용자 목표 완료로 표시하지 않는다. 2단계 구현·검증 이후 같은 문서를 다시 갱신한다. Map의 1단계 사용자 제외와 Claude 별도 빌드 소유권은 유지하며 이 문서 작업자가 새 Map 작업을 시작하지 않는다.

## 8. 전체 직접 의존성: 기준선 → 최종 merged 소스

아래 **412개 선언 행**은 각 고정 기준선과 2절의 **최종 merged SHA**에서 Git으로 읽은 package.json의 dependencies·devDependencies·peerDependencies·optionalDependencies 전체 합집합이다. Transport 관리자만 후속PR186의 최종 운영 mergedf30dbd82를 사용하며 주PR181의 package blob·선언값과 동일함을 확인했다. 같은 이름이 서로 다른 종류에 선언되면 각각 표시한다. 이10개 package에는 양 시점 모두 peer/optional 직접 선언이 없다. 변경 없는 직접 의존성도 생략하지 않았다. `없음`은 기준선에 없는 신규 선언, `제거`는 최종 선언에서 삭제를 뜻한다.

이는 **선언 전체 비교**이며 모든 전이 의존성 목록이나 lock의 실제 설치 전체 목록은 아니다. file: 선언은 위 버전·SRI 원장으로 해석한다. 연결 workspace SDK의 `*`는 해당 merged tree의 내부 package 계약으로 해석하며 외부 공유 라이브러리의 정확 버전 고정을 완화하는 표기가 아니다. 실제 stale cache·중복 설치·SRI는 별도 guard와 파일 대조로 검증했다.

<details>
<summary>Geo — 기준 eab5f7a7 → 최종 merged 786dae25 (51개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-geo/blob/eab5f7a7a7f495b32ebffdf201d6326c3ff0034d/kor-travel-geo-ui/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-geo/blob/786dae25f0a1927a98cbc66e6e8c86987da0a42f/kor-travel-geo-ui/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @hookform/resolvers | 실행 | `5.9.2` | `7.0.5` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.6.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| @tanstack/react-table | 실행 | `8.21.3` | `9.3.1` |
| @tanstack/react-virtual | 실행 | `3.14.22` | `3.14.26` |
| class-variance-authority | 실행 | `0.7.1` | `0.7.1` |
| clsx | 실행 | `2.1.1` | `2.1.1` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| maplibre-gl | 실행 | `6.15.0` | `6.17.0` |
| maplibre-vworld-react | 실행 | `file:vendor/maplibre-vworld-react-ffa5523b5f4f.tgz` | `제거` |
| next | 실행 | `16.4.3` | `16.4.6` |
| pretendard | 실행 | `없음` | `1.3.9` |
| radix-ui | 실행 | `1.8.1` | `1.8.1` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `7.91.0` | `7.92.0` |
| tailwind-merge | 실행 | `3.7.0` | `3.7.0` |
| undici | 실행 | `8.12.3` | `8.12.4` |
| vworld-map-core | 실행 | `없음` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `없음` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `4.6.7` | `4.6.7` |
| zustand | 실행 | `5.0.16` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @testing-library/jest-dom | 개발 | `7.0.1` | `7.0.1` |
| @testing-library/react | 개발 | `16.3.3` | `16.3.3` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| @vitejs/plugin-react | 개발 | `6.1.2` | `6.3.0` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-next | 개발 | `16.4.3` | `제거` |
| eslint-import-resolver-typescript | 개발 | `없음` | `4.4.5` |
| eslint-plugin-import-x | 개발 | `없음` | `4.18.1` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-dom | 개발 | `없음` | `5.30.1` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| eslint-plugin-react-x | 개발 | `없음` | `5.30.1` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| openapi-typescript | 개발 | `7.13.0` | `7.13.0` |
| postcss | 개발 | `8.5.31` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Map admin — 기준 32668d00 → 최종 merged f347b353 (51개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-map/blob/32668d003ea6a259468e03970bd167359c19ecdb/packages/kor-travel-map-admin/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-map/blob/f347b353fb13fe83ffbdfdacb894b2bfa9ebcb87/packages/kor-travel-map-admin/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `1.9.0` | `제거` |
| @hookform/resolvers | 실행 | `없음` | `7.0.5` |
| @kor-travel-map/map-marker-react | 실행 | `*` | `*` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.9.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| @tanstack/react-table | 실행 | `8.21.3` | `9.3.1` |
| @tanstack/react-virtual | 실행 | `3.14.22` | `3.14.26` |
| class-variance-authority | 실행 | `0.7.1` | `0.7.1` |
| clsx | 실행 | `2.1.1` | `2.1.1` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| maplibre-gl | 실행 | `6.15.0` | `6.17.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| pretendard | 실행 | `1.3.9` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| sonner | 실행 | `2.0.8` | `2.0.8` |
| tailwind-merge | 실행 | `3.7.0` | `3.7.0` |
| tw-animate-css | 실행 | `1.4.0` | `1.4.0` |
| vworld-map-core | 실행 | `없음` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `없음` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `없음` | `4.6.7` |
| zustand | 실행 | `5.0.16` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `16.4.3` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @testing-library/dom | 개발 | `10.4.2` | `10.4.2` |
| @testing-library/react | 개발 | `16.3.3` | `16.3.3` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| @vitejs/plugin-react | 개발 | `6.1.2` | `6.3.0` |
| eslint | 개발 | `10.13.0` | `10.14.0` |
| eslint-import-resolver-typescript | 개발 | `4.4.5` | `4.4.5` |
| eslint-plugin-import-x | 개발 | `4.17.1` | `4.18.1` |
| eslint-plugin-jsx-a11y-x | 개발 | `0.2.0` | `0.2.0` |
| eslint-plugin-react-dom | 개발 | `5.28.8` | `5.30.1` |
| eslint-plugin-react-hooks | 개발 | `7.1.1` | `7.1.1` |
| eslint-plugin-react-x | 개발 | `5.28.8` | `5.30.1` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| openapi-typescript | 개발 | `7.13.0` | `7.13.0` |
| react-doctor | 개발 | `0.9.1` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `8.72.0` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vite-tsconfig-paths | 개발 | `6.1.1` | `6.1.1` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Map SDK — 기준 32668d00 → 최종 merged f347b353 (2개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-map/blob/32668d003ea6a259468e03970bd167359c19ecdb/packages/kor-travel-map-user-client/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-map/blob/f347b353fb13fe83ffbdfdacb894b2bfa9ebcb87/packages/kor-travel-map-user-client/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| openapi-typescript | 개발 | `7.13.0` | `7.13.0` |
| typescript | 개발 | `5.9.3` | `5.9.3` |

</details>

<details>
<summary>Weather — 기준 b55857f7 → 최종 merged faca2cee (40개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-weather/blob/b55857f7e40fc4f649e65a57172beafda4af8b62/packages/kor-travel-weather-admin/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-weather/blob/faca2ceee39a116dfea0680e2a5e1d8ced198cf1/packages/kor-travel-weather-admin/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `1.9.0` | `제거` |
| @hookform/resolvers | 실행 | `없음` | `7.0.5` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.9.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-dropdown-menu | 실행 | `2.2.1` | `제거` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| maplibre-gl | 실행 | `6.15.0` | `6.17.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| pretendard | 실행 | `없음` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| vworld-map-core | 실행 | `없음` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `없음` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `없음` | `4.6.7` |
| zustand | 실행 | `없음` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-next | 개발 | `16.4.3` | `제거` |
| eslint-import-resolver-typescript | 개발 | `없음` | `4.4.5` |
| eslint-plugin-import-x | 개발 | `없음` | `4.18.1` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-dom | 개발 | `없음` | `5.30.1` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| eslint-plugin-react-x | 개발 | `없음` | `5.30.1` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| postcss | 개발 | `없음` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Concierge — 기준 44383287 → 최종 merged f2db107c (43개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-concierge/blob/4438328704be15592c47281cd19b525e91567767/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-concierge/blob/f2db107cc4bfb58115b890ea6198a2fe0c321e17/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `^1.8.0` | `제거` |
| @hookform/resolvers | 실행 | `5.9.1` | `7.0.5` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.9.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `^5.40.0` | `5.107.1` |
| class-variance-authority | 실행 | `^0.7.1` | `0.7.1` |
| clsx | 실행 | `^2.1.1` | `2.1.1` |
| lucide-react | 실행 | `^1.17.0` | `1.72.0` |
| maplibre-gl | 실행 | `^6.0.0` | `6.17.0` |
| next | 실행 | `^16.2.7` | `16.4.6` |
| pretendard | 실행 | `1.3.9` | `1.3.9` |
| react | 실행 | `^19.2.8` | `19.3.1` |
| react-dom | 실행 | `^19.2.8` | `19.3.1` |
| react-hook-form | 실행 | `^7.51.5` | `7.92.0` |
| shadcn | 실행 | `^4.10.0` | `제거` |
| tailwind-merge | 실행 | `^3.6.0` | `3.7.0` |
| vworld-map-core | 실행 | `file:vendor/vworld-map-core-1.0.0.tgz` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `file:vendor/vworld-map-web-1.0.0.tgz` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `^4.4.3` | `4.6.7` |
| zustand | 실행 | `없음` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @tailwindcss/postcss | 개발 | `^4.3.1` | `4.3.5` |
| @testing-library/user-event | 개발 | `없음` | `14.6.9` |
| @types/node | 개발 | `^20` | `22.20.5` |
| @types/react | 개발 | `^19.2.17` | `19.3.0` |
| @types/react-dom | 개발 | `^19.2.3` | `19.3.0` |
| autoprefixer | 개발 | `^10.4.19` | `제거` |
| eslint | 개발 | `^9.39.4` | `10.14.0` |
| eslint-config-next | 개발 | `^16.2.7` | `제거` |
| eslint-import-resolver-typescript | 개발 | `없음` | `4.4.5` |
| eslint-plugin-import-x | 개발 | `없음` | `4.18.1` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| jsdom | 개발 | `없음` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| postcss | 개발 | `^8.4.38` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `^4.3.1` | `4.3.5` |
| tw-animate-css | 개발 | `^1.4.0` | `1.4.0` |
| typescript | 개발 | `^5.4.5` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vitest | 개발 | `^4.1.9` | `5.1.0` |

</details>

<details>
<summary>Docker Manager — 기준 351e15b4 → 최종 merged 9910b9a6 (39개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-docker-manager/blob/351e15b4d518daca48e83d2436fc8f1bdf39551c/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-docker-manager/blob/9910b9a6dba902c6a59469d3a6f46c6077e78d3f/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @kor-travel/tokens | 실행 | `없음` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `없음` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| pretendard | 실행 | `없음` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| recharts | 실행 | `3.10.1` | `3.10.1` |
| zod | 실행 | `없음` | `4.6.7` |
| zustand | 실행 | `없음` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `없음` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @testing-library/dom | 개발 | `10.4.2` | `10.4.2` |
| @testing-library/jest-dom | 개발 | `7.0.1` | `7.0.1` |
| @testing-library/react | 개발 | `16.3.3` | `16.3.3` |
| @testing-library/user-event | 개발 | `14.6.8` | `14.6.9` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| @vitejs/plugin-react | 개발 | `6.1.2` | `6.3.0` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-next | 개발 | `16.4.3` | `제거` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-dom | 개발 | `없음` | `5.30.1` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| eslint-plugin-react-x | 개발 | `없음` | `5.30.1` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| postcss | 개발 | `8.5.31` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Pinvi web/admin — 기준 d42ac953 → 최종 merged dd3bcd18 (56개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/pinvi/blob/d42ac95300749df955ce9e2bb63ea62eba36da09/apps/web/package.json) · [최종 merged package.json](https://github.com/digitie/pinvi/blob/dd3bcd18ce573e6ddf784864d63901352e7e05d3/apps/web/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `1.9.0` | `제거` |
| @hookform/resolvers | 실행 | `5.9.2` | `7.0.5` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.9.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @pinvi/api-client | 실행 | `*` | `*` |
| @pinvi/design-tokens | 실행 | `*` | `*` |
| @pinvi/domain | 실행 | `*` | `*` |
| @pinvi/hooks | 실행 | `*` | `*` |
| @pinvi/i18n | 실행 | `*` | `*` |
| @pinvi/schemas | 실행 | `*` | `*` |
| @pinvi/state | 실행 | `*` | `*` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| @tanstack/react-table | 실행 | `8.21.3` | `9.3.1` |
| @tanstack/react-virtual | 실행 | `3.14.22` | `3.14.26` |
| class-variance-authority | 실행 | `0.7.1` | `0.7.1` |
| clsx | 실행 | `2.1.1` | `2.1.1` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| maplibre-gl | 실행 | `6.15.0` | `6.17.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| next-intl | 실행 | `4.14.9` | `4.15.0` |
| pretendard | 실행 | `1.3.9` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `7.91.0` | `7.92.0` |
| tailwind-merge | 실행 | `3.7.0` | `3.7.0` |
| vworld-map-core | 실행 | `file:../mobile/vendor/vworld-map-core-1.0.0.tgz` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `file:vendor/vworld-map-web-1.0.2.tgz` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `4.6.7` | `4.6.7` |
| zustand | 실행 | `5.0.16` | `5.1.0` |
| @axe-core/playwright | 개발 | `4.14.0` | `4.14.0` |
| @eslint-react/eslint-plugin | 개발 | `없음` | `5.30.1` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @testing-library/jest-dom | 개발 | `7.0.1` | `7.0.1` |
| @testing-library/react | 개발 | `16.3.3` | `16.3.3` |
| @testing-library/user-event | 개발 | `14.6.8` | `14.6.9` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.2.18` | `19.3.0` |
| @types/react-dom | 개발 | `19.2.7` | `19.3.0` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-next | 개발 | `16.4.3` | `제거` |
| eslint-plugin-import-x | 개발 | `없음` | `4.18.1` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| globals | 개발 | `없음` | `17.14.0` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| postcss | 개발 | `8.5.31` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Pinvi mobile — 기준 d42ac953 → 최종 merged dd3bcd18 (51개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/pinvi/blob/d42ac95300749df955ce9e2bb63ea62eba36da09/apps/mobile/package.json) · [최종 merged package.json](https://github.com/digitie/pinvi/blob/dd3bcd18ce573e6ddf784864d63901352e7e05d3/apps/mobile/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @kor-travel/tokens | 실행 | `없음` | `file:../web/vendor/kor-travel-tokens-0.1.1.tgz` |
| @maplibre/maplibre-react-native | 실행 | `11.5.0` | `11.5.1` |
| @pinvi/api-client | 실행 | `*` | `*` |
| @pinvi/design-tokens | 실행 | `*` | `*` |
| @pinvi/domain | 실행 | `*` | `*` |
| @pinvi/hooks | 실행 | `*` | `*` |
| @pinvi/i18n | 실행 | `*` | `*` |
| @pinvi/schemas | 실행 | `*` | `*` |
| @pinvi/state | 실행 | `*` | `*` |
| @react-native-async-storage/async-storage | 실행 | `2.2.0` | `3.1.1` |
| @tanstack/react-query | 실행 | `5.104.5` | `5.107.1` |
| expo | 실행 | `57.0.32` | `58.0.24` |
| expo-build-properties | 실행 | `57.0.23` | `58.0.12` |
| expo-constants | 실행 | `57.0.23` | `58.0.16` |
| expo-dev-client | 실행 | `57.0.21` | `58.0.19` |
| expo-font | 실행 | `없음` | `58.0.12` |
| expo-linking | 실행 | `57.0.13` | `58.0.17` |
| expo-location | 실행 | `57.0.23` | `58.0.21` |
| expo-router | 실행 | `57.0.30` | `58.0.31` |
| expo-secure-store | 실행 | `57.0.4` | `58.0.3` |
| expo-status-bar | 실행 | `57.0.1` | `58.0.5` |
| expo-web-browser | 실행 | `57.0.3` | `58.0.8` |
| nativewind | 실행 | `4.2.7` | `5.0.0-rc.1` |
| pretendard | 실행 | `없음` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| react-native | 실행 | `0.86.3` | `0.88.1` |
| react-native-css | 실행 | `없음` | `3.1.0-rc.1` |
| react-native-reanimated | 실행 | `4.7.1` | `4.7.1` |
| react-native-safe-area-context | 실행 | `5.7.0` | `5.11.1` |
| react-native-screens | 실행 | `4.26.2` | `4.30.1` |
| react-native-web | 실행 | `0.21.4` | `0.21.4` |
| react-native-worklets | 실행 | `0.13.0` | `0.13.1` |
| vworld-map-core | 실행 | `file:vendor/vworld-map-core-1.0.0.tgz` | `file:../web/vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-rn | 실행 | `file:vendor/vworld-map-rn-1.0.0.tgz` | `file:../web/vendor/vworld-map-rn-1.0.1.tgz` |
| vworld-map-web | 실행 | `없음` | `file:../web/vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `4.6.7` | `4.6.7` |
| zustand | 실행 | `5.0.16` | `5.1.0` |
| @babel/core | 개발 | `7.29.7` | `7.29.7` |
| @tailwindcss/postcss | 개발 | `없음` | `4.3.5` |
| @types/react | 개발 | `19.2.18` | `19.3.0` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-expo | 개발 | `57.0.2` | `제거` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| lightningcss | 개발 | `없음` | `file:../web/vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| postcss | 개발 | `없음` | `8.5.32` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `3.4.19` | `4.3.5` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |

</details>

<details>
<summary>Transport public — 기준 59e1d821 → 최종 merged 936fdb90 (39개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-transport/blob/59e1d8213c09a82a4ed9cc4396a6414ef0332b9c/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-transport/blob/936fdb90b0ee9f6392d2f888255053ee1f4066b2/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `1.9.0` | `제거` |
| @kor-travel/tokens | 실행 | `없음` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `없음` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| @tailwindcss/postcss | 실행 | `4.3.3` | `4.3.5` |
| class-variance-authority | 실행 | `0.7.1` | `0.7.1` |
| cn | 실행 | `0.5.0` | `제거` |
| date-fns | 실행 | `4.4.0` | `4.4.0` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| postcss | 실행 | `8.5.31` | `8.5.32` |
| pretendard | 실행 | `없음` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-day-picker | 실행 | `10.0.2` | `10.0.2` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| shadcn | 실행 | `4.22.1` | `제거` |
| tailwindcss | 실행 | `4.3.3` | `4.3.5` |
| tw-animate-css | 실행 | `1.4.0` | `1.4.0` |
| zod | 실행 | `없음` | `4.6.7` |
| zustand | 실행 | `없음` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @testing-library/jest-dom | 개발 | `7.0.1` | `7.0.1` |
| @testing-library/react | 개발 | `16.3.3` | `16.3.3` |
| @testing-library/user-event | 개발 | `14.6.8` | `14.6.9` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| eslint | 개발 | `없음` | `10.14.0` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>

<details>
<summary>Transport admin — 기준 59e1d821 → 최종 merged f30dbd82 (40개 선언)</summary>

정본: [기준선 package.json](https://github.com/digitie/kor-travel-transport/blob/59e1d8213c09a82a4ed9cc4396a6414ef0332b9c/packages/kor-travel-transport-admin/frontend/package.json) · [최종 merged package.json](https://github.com/digitie/kor-travel-transport/blob/f30dbd823614399d6dc671eb1f1bf4d8f46c6064/packages/kor-travel-transport-admin/frontend/package.json).

| 라이브러리 | 종류 | 기준선 선언 | 최종 merged 선언 |
|---|---|---|---|
| @base-ui/react | 실행 | `1.9.0` | `제거` |
| @kor-travel/parking-ui | 실행 | `file:../../../frontend/src` | `file:../../../frontend/src` |
| @kor-travel/tokens | 실행 | `file:vendor/kor-travel-tokens-0.1.0.tgz` | `file:vendor/kor-travel-tokens-0.1.1.tgz` |
| @kor-travel/ui | 실행 | `file:vendor/kor-travel-ui-0.1.0-dev.9.tgz` | `file:vendor/kor-travel-ui-0.2.0.tgz` |
| @radix-ui/react-focus-scope | 실행 | `없음` | `file:vendor/radix-ui-react-focus-scope-1.3.1+kortravel.fix.2.tgz` |
| class-variance-authority | 실행 | `0.7.1` | `0.7.1` |
| clsx | 실행 | `2.1.1` | `2.1.1` |
| echarts | 실행 | `6.1.0` | `6.1.0` |
| lucide-react | 실행 | `1.61.0` | `1.72.0` |
| maplibre-gl | 실행 | `6.15.0` | `6.17.0` |
| next | 실행 | `16.4.3` | `16.4.6` |
| pretendard | 실행 | `없음` | `1.3.9` |
| react | 실행 | `19.3.1` | `19.3.1` |
| react-dom | 실행 | `19.3.1` | `19.3.1` |
| react-hook-form | 실행 | `없음` | `7.92.0` |
| tailwind-merge | 실행 | `3.7.0` | `3.7.0` |
| vworld-map-core | 실행 | `file:vendor/vworld-map-core-1.0.0.tgz` | `file:vendor/vworld-map-core-1.0.1.tgz` |
| vworld-map-web | 실행 | `file:vendor/vworld-map-web-1.0.1.tgz` | `file:vendor/vworld-map-web-1.0.3.tgz` |
| zod | 실행 | `없음` | `4.6.7` |
| zustand | 실행 | `없음` | `5.1.0` |
| @next/eslint-plugin-next | 개발 | `없음` | `16.4.6` |
| @playwright/test | 개발 | `1.64.1` | `1.65.0` |
| @tailwindcss/postcss | 개발 | `4.3.3` | `4.3.5` |
| @types/node | 개발 | `22.20.5` | `22.20.5` |
| @types/react | 개발 | `19.3.0` | `19.3.0` |
| @types/react-dom | 개발 | `19.3.0` | `19.3.0` |
| @types/supercluster | 개발 | `7.1.3` | `7.1.3` |
| eslint | 개발 | `9.39.5` | `10.14.0` |
| eslint-config-next | 개발 | `16.4.3` | `제거` |
| eslint-plugin-jsx-a11y-x | 개발 | `없음` | `0.2.0` |
| eslint-plugin-react-hooks | 개발 | `없음` | `7.1.1` |
| jsdom | 개발 | `30.1.3` | `31.0.0` |
| lightningcss | 개발 | `없음` | `file:vendor/lightningcss-1.33.0+nativecss.fix.4.tgz` |
| react-doctor | 개발 | `없음` | `0.9.22` |
| tailwindcss | 개발 | `4.3.3` | `4.3.5` |
| tw-animate-css | 개발 | `1.4.0` | `1.4.0` |
| typescript | 개발 | `5.9.3` | `5.9.3` |
| typescript-eslint | 개발 | `없음` | `8.72.2` |
| vite | 개발 | `8.3.5` | `8.3.8` |
| vitest | 개발 | `5.0.5` | `5.1.0` |

</details>


### 8.1 Workspace root에서 추가로 강제하는 계약

Pinvi는 npm12.0.1 root lock을 사용한다. root expo58.0.24/router58.0.31 선언도 모바일 최종값과 같고, react/react-dom19.3.1·RN0.88.1·ESLint10.14.0·CSS엔진·FocusScope를 root override로 묶는다. Scope와 Lightning CSS는 직접 file: 의존성을 참조하는 `$@radix-ui/react-focus-scope`·`$lightningcss` override를 사용해 nested copy까지 같은 원본을 적용한다. native에 DOM Scope 직접 의존성을 추가한 것이 아니다.

Map root 역시 같은 Scope/CSS file: override와 npm12.0.1 도구 계약을 갖는다. 이 내용은 최종1496 tree의 읽기 전용 조사이며 새 Map 변경이 아니다. Manager 후속 SDK590은 frontend package의 직접 의존성 blob을 바꾸지 않았다.

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
