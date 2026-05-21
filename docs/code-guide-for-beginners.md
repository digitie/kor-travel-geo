# 처음 보는 사람을 위한 코드 안내

이 프로젝트는 크게 세 계층으로 나뉜다.

## 라이브러리

`src/kraddr/geo`에는 Python 패키지가 들어 있다.

- `data.py`: 도로명주소 아카이브 다운로드와 파싱
- `legal_dong.py`: 법정동 코드 API 파싱
- `reverse.py`: 내비게이션 TXT 파싱과 단순 역지오코더 보조 함수
- `spatialite.py`: SQLite/SpatiaLite 스키마, 로더, 지오코딩, 역지오코딩, 우편번호 조회
- `dto.py`: 주소 지오코딩 요청/응답 DTO

현재 GIS 동작을 이해하려면 `spatialite.py`부터 보는 것이 가장 빠르다.

## 디버그 UI 백엔드

`debug-ui/src/kraddr_geo_debug_api`는 store를 FastAPI로 노출한다.

- `config.py`: 환경 변수
- `database.py`: 공유 `SpatialiteAddressStore` 인스턴스와 조회 보조 함수
- `ingest.py`: 수동 업로드 적재 작업, 파일 분류, 진행 상태 스냅샷
- `main.py`: HTTP 라우트

## 디버그 UI 웹

`debug-ui/web/`은 Next.js 주소 탐색 UI다. 기존 사용자 흐름인 샘플 검색, 전체 주소 목록, 페이지 이동, 지도 미리보기, 레이어 전환, 수동 파일 업로드 적재를 유지한다.

## 일반 개발 흐름

```powershell
python -m pytest -q
python -m ruff check .
cd debug-ui/web
npm run lint
npm run test
npm run build
```

실데이터 검증은 먼저 `data/juso`를 로컬 SQLite 파일로 적재한 뒤 `SpatialiteAddressStore` 함수를 직접 호출해 지오코딩, 역지오코딩, 우편번호 조회, 인덱스 계획을 확인한다.
