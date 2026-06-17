# ADR-019: 프론트엔드 런타임은 Next.js 16을 보안 하한선으로 둔다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: codex, PR #12 구현

## 컨텍스트

초기 문서는 `kor-travel-geo-ui`를 Next.js 14 기반으로 설계했다. 그러나 PR #12에서 실제 패키지를 부트스트랩하며 `npm audit --omit=dev`를 실행한 결과, Next.js 14 계열에는 2026년 기준 production high advisory가 남아 있었다. 신규 UI를 처음 도입하는 시점에 이미 high 취약점이 보고된 major를 고정하면, 내부망 전용 도구라 해도 운영 배포 전 보안 검토에서 다시 major upgrade를 요구받을 가능성이 높다.

## 결정

`kor-travel-geo-ui`는 Next.js 16을 보안 하한선으로 둔다. React는 Next.js 16.2.6의 peer 범위가 허용하는 React 18.3.1을 유지한다. Node.js는 Next.js 16의 engine 조건에 맞춰 20.9 이상을 사용한다.

## 근거

- Next.js 16.2.6은 npm registry 기준 React 18과 React 19를 모두 peer로 허용한다.
- 기존 App Router 구조, Route Handler 프록시, TanStack Query 기반 클라이언트 컴포넌트는 Next.js 16에서도 큰 구조 변경 없이 동작한다.
- `npm audit --omit=dev --audit-level=high`가 통과하도록 high 취약점은 제거한다. Next.js 내부 `postcss` moderate advisory는 upstream dependency 해결 전까지 PR 본문에 잔여 위험으로 남긴다.

## 결과

- 프론트엔드 문서의 프레임워크 표기는 Next.js 16으로 갱신한다.
- CI는 Node.js 20을 사용하고 `npm ci`, `npm run gen:types`, `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 실행한다.
- 향후 Next.js minor/patch 업데이트는 `npm audit --omit=dev --audit-level=high`를 기준으로 빠르게 흡수한다.
