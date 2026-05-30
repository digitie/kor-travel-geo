# T-069 Consistency case(C1~C10) 전환 시 프리즈 수정

- 상태: 완료
- 날짜: 2026-05-31
- 관련 UI: `kraddr-geo-ui` `/admin/consistency`

## 증상

`/admin/consistency`에서 좌측 case 레일의 C1~C10 버튼을 마우스로 클릭해 case를 이동하면 탭이 멈춘다. T-066/T-068에서 지도 마운트 시점과 ResizeObserver 루프를 고쳤지만, case 전환 프리즈는 별개의 원인으로 남아 있었다.

## 근본 원인

`ConsistencyPanel`이 매 렌더에서 다음과 같이 `samples`를 만들었다.

```ts
const samples = samplesQuery.data?.items ?? [];
```

case를 전환하면 `samplesQuery`의 query key가 바뀌어 재요청(refetch)이 발생하고, 그 사이 `samplesQuery.data`가 잠깐 `undefined`가 된다. 그러면 `?? []`가 **매 렌더마다 새 배열 참조**를 만들어 `useReactTable({ data: samples })`에 넘긴다. TanStack Table은 `data` 참조가 바뀌면 auto-reset 동작으로 내부 `setState`를 호출하므로, "새 배열 → setState → 리렌더 → 또 새 배열 → …"의 **무한 리렌더 루프**가 생긴다. 메인 스레드가 점유되어 `requestAnimationFrame`도 돌지 못하고 탭이 멈춘다.

- 진단: Windows Playwright로 case 버튼 실제 클릭 시 프리즈 재현. CDP 트레이스에서 시간의 100%가 JS(`v8.callFunction`)였고, 핫 프레임 1위가 react-dom의 `prepareFreshStack`(렌더 재시작)으로, 무한 리렌더임을 확인했다. dev 모드에서 렌더 카운터를 넣어 `ConsistencyPanel`이 루프의 진원지임을 좁혔다.
- "Maximum update depth exceeded" 에러가 안 뜬 이유: 업데이트가 동기 중첩이 아니라 스케줄러를 통해 task 단위로 반복되어 React의 중첩 업데이트 가드(50회)에 걸리지 않고 무한히 렌더만 반복했다.

## 수정

`samples` 참조를 안정화한다.

```ts
const EMPTY_SAMPLES: ConsistencyCaseSample[] = []; // 모듈 스코프 고정 참조
...
const samples = useMemo(
  () => samplesQuery.data?.items ?? EMPTY_SAMPLES,
  [samplesQuery.data]
);
```

데이터가 없을 때도 항상 같은 빈 배열을 쓰고, 데이터가 있으면 query 데이터가 바뀔 때만 참조가 바뀐다. 더 이상 매 렌더마다 새 `data`가 들어가지 않아 auto-reset 루프가 사라진다.

## 검증

- Windows Playwright로 C1~C10을 실제 클릭으로 2바퀴(20회) 전환: 모든 클릭 응답성 1~18ms, 프리즈 0건.
- `tests/unit/consistency-panel.test.tsx`에 case 전환 회귀 테스트 추가(루프가 재발하면 타임아웃으로 실패). `npm run test -- consistency-panel` → 2 passed.
- `npm run lint`, `npm run build`(프로덕션 빌드) 통과.
