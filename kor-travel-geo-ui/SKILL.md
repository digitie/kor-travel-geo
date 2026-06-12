# SKILL — kor-travel-geo-ui

## 원칙

- DB 드라이버를 추가하지 않는다. 모든 데이터 접근은 백엔드 REST API를 통한다.
- 내부망 전용 도구다. 애플리케이션 인증은 두지 않는다.
- `openapi.json`이 바뀌면 `npm run gen:types`를 실행한다.
- 화면은 운영 도구답게 조밀하고 예측 가능하게 유지한다. 마케팅 랜딩 페이지를 만들지 않는다.

## 검증

프론트엔드 실행과 정적 검증은 WSL ext4 테스트 미러의 Linux Node/npm에서 수행한다. Playwright e2e와 실제 브라우저 검증은 Windows Node/브라우저에서만 수행하고, Windows Playwright를 WSL UI 서버에 붙인다.

```bash
npm run type-check
npm run test
npm run build
npx react-doctor@latest . --offline --verbose --json
```

모든 프론트엔드 작업 뒤에는 React Doctor를 실행하고, 새 경고가 나오면 수정한 뒤 재실행한다.
