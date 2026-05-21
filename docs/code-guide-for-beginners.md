# 처음 보는 사람을 위한 코드 안내

이 프로젝트는 크게 세 계층으로 나뉜다.

## 라이브러리

`src/kraddr/geo`에는 Python package가 들어 있다.

- `data.py`: 도로명주소 archive 다운로드와 parsing
- `legal_dong.py`: 법정동 코드 API parsing
- `reverse.py`: 내비게이션 TXT parsing과 단순 reverse geocoder helper
- `spatialite.py`: SQLite/SpatiaLite 스키마, loader, geocoding, reverse geocoding, 우편번호 조회
- `dto.py`: 주소 geocoding 요청/응답 DTO

현재 GIS 동작을 이해하려면 `spatialite.py`부터 보는 것이 가장 빠르다.

## Debug UI Backend

`debug-ui/src/kraddr_geo_debug_api`는 store를 FastAPI로 노출한다.

- `config.py`: 환경 변수
- `database.py`: 공유 `SpatialiteAddressStore` instance와 query helper
- `ingest.py`: 수동 upload load job, 파일 분류, progress snapshot
- `main.py`: HTTP route

## Debug UI Web

`debug-ui/web/`은 Next.js 주소 탐색 UI다. 기존 사용자 흐름인 sample search, 전체 주소 목록, paging, map preview, layer toggle, 수동 파일 upload loading을 유지한다.

## 일반 개발 흐름

```powershell
python -m pytest -q
python -m ruff check .
cd debug-ui/web
npm run lint
npm run test
npm run build
```

실데이터 검증은 먼저 `data/juso`를 로컬 SQLite 파일로 적재한 뒤 `SpatialiteAddressStore` 함수를 직접 호출해 geocoding, reverse geocoding, 우편번호 조회, index plan을 확인한다.
