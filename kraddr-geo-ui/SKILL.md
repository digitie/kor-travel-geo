# SKILL — kraddr-geo-ui

## 원칙

- DB 드라이버를 추가하지 않는다. 모든 데이터 접근은 백엔드 REST API를 통한다.
- 내부망 전용 도구다. 애플리케이션 인증은 두지 않는다.
- `openapi.json`이 바뀌면 `npm run gen:types`를 실행한다.
- 화면은 운영 도구답게 조밀하고 예측 가능하게 유지한다. 마케팅 랜딩 페이지를 만들지 않는다.

## 검증

```bash
npm run type-check
npm run test
npm run build
```
