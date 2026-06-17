# UI 디자인 규칙

이 문서는 `https://styleseed-demo.vercel.app/llms.txt`와 그 전체 문맥인
`https://styleseed-demo.vercel.app/llms-full.txt`를 `kor-travel-geo-ui`에 맞게
해석한 운영 콘솔용 규칙이다. StyleSeed는 제품 UI가 "생성된 화면"처럼 보이지 않도록
단일 accent, 의미 토큰, 카드 구조, 낮은 그림자, 일관된 모션을 강조한다.

## 적용 범위

`kor-travel-geo-ui`는 내부 운영 콘솔이다. 따라서 마케팅식 hero, 장식적 gradient, 큰 CTA보다
스캔하기 쉬운 정보 밀도와 예측 가능한 조작을 우선한다. StyleSeed의 모바일/핀테크 예시는
그대로 복사하지 않고, 아래 규칙만 공통 토큰과 primitive에 적용한다.

## 핵심 규칙

1. 색상은 단일 accent 중심으로 쓴다.
   `--brand`는 active nav, 진행률 fill, 선택 상태, 작은 icon/badge에만 쓴다. 큰 배경면은
   `--surface-*` 토큰을 사용하고, 오류/경고/성공 색은 작은 badge, dot, text에 제한한다.

2. 텍스트는 5단계 grayscale 토큰을 따른다.
   `--text-strong`, `--text-primary`, `--text-secondary`, `--text-tertiary`,
   `--text-disabled`를 사용한다. 순수 `#000`과 임의 gray 값은 새로 늘리지 않는다.

3. 카드와 패널은 정보 단위의 경계다.
   운영 화면의 주요 내용은 `Panel`, `Card`, table, map 같은 명확한 영역 안에 둔다. 다만 이
   프로젝트의 기존 디자인 시스템은 카드 반경을 8px로 유지하므로 StyleSeed 예시의 16px
   카드 반경은 적용하지 않는다.

4. 그림자는 아주 약하게 쓴다.
   기본 카드는 `--shadow-card`처럼 4% 수준의 낮은 그림자만 사용한다. modal이나 floating
   표면도 12%를 넘기지 않는다. 색이 들어간 그림자는 쓰지 않는다.

5. 조작 대상은 최소 44px touch target을 가진다.
   button, input, nav link, icon button, checkbox hit area는 `min-height: 44px` 또는 그에
   준하는 hit area를 가진다. 시각적으로 작은 checkbox도 pseudo hit area로 클릭 영역을 보강한다.

6. label은 작고 일관되게 표시한다.
   폼 label, table header, nav group title은 12px, 굵은 weight, `letter-spacing: 0.05em`,
   uppercase를 기본으로 한다. 한국어 문구는 형태가 바뀌지 않지만 같은 시각 리듬을 유지한다.

7. 상태 표시는 dot과 text를 함께 쓴다.
   `StatusBadge` 계열은 색만으로 상태를 전달하지 않고 같은 색의 6px dot과 text를 함께 보여 준다.
   큰 warning/error 배경면은 필요한 안내 박스에만 아주 옅게 사용한다.

8. 숫자는 더 크게, 보조 라벨은 더 작게 둔다.
   KPI 성격의 `.metric strong`은 36px, label은 12px uppercase로 둔다. 숫자와 단위를 함께
   보여 줄 때는 줄바꿈이 생기지 않게 `white-space: nowrap` 계열을 사용한다.

9. 모션은 이름 있는 토큰으로 제한한다.
   hover/focus/press 전환은 `--duration-fast`, `--duration-normal`, `--ease-default`를 사용한다.
   `prefers-reduced-motion: reduce`에서는 animation과 transition을 사실상 비활성화한다.

10. 새 UI는 semantic token부터 확인한다.
    새 컴포넌트에서 hardcoded hex를 추가하기 전에 `app/globals.css`와 `tailwind.config.ts`의
    `surface`, `text`, `brand`, `success`, `warn`, `danger` 토큰으로 표현할 수 있는지 먼저 본다.

## 금지

- 순수 검정(`#000`, `text-black`, `bg-black`) 추가
- 브랜드색을 큰 카드 배경, page background, 여러 섹션의 큰 면으로 사용
- 카드 안에 카드를 중첩하거나, page section 자체를 장식용 floating card로 남발
- 선택 UI를 임의 dropdown/radio/checkbox filter로 늘리기. 2-4개 옵션은 segmented/pill,
  그 이상은 별도 필터 영역이나 페이지로 분리한다.
- 보이는 강한 shadow, 색이 들어간 shadow, 컴포넌트마다 다른 shadow 언어
- viewport width에 비례한 font-size 조정

## 현재 코드 적용 지점

- `app/globals.css`: surface/text/status/motion/shadow token과 기존 class 기반 UI 규칙
- `tailwind.config.ts`: 새 UI에서 사용할 semantic color token
- `components/ui/button.tsx`, `input.tsx`, `checkbox.tsx`, `label.tsx`, `card.tsx`:
  shadcn 기반 primitive의 touch target, label, shadow, radius, motion 규칙
