# kraddr-geo 웹

Next.js 기반 주소 브라우저입니다. 샘플 데이터와 FastAPI 백엔드의 실제 SpatiaLite 주소 목록을 같은 화면에서 확인할 수 있습니다.

## 실행

```powershell
cd debug-ui/web
npm install
npm run dev
```

기본 API 주소는 `http://127.0.0.1:3011`입니다. 다른 주소를 쓰려면 `.env.local`에 설정합니다.

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:3011
```

## 화면 기능

- 전체 주소 목록 페이지네이션
- 도로명/지번/코드 검색 범위 전환
- Kakao 지도 표시
- 경계/반경 레이어 토글
- 백엔드 오류 표시와 새로고침
- 여러 TXT/ZIP/7Z/SHP 파일 끌어 놓기 수동 적재
- 적재 작업 진행률, 현재 파일, 로드/스킵 건수, 오류 표시

## 테스트

```powershell
npm run lint
npm run test
npm run build
```
