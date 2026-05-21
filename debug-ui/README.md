# kraddr-geo 디버그 UI

`debug-ui`는 SQLite + SpatiaLite 파일을 읽어 주소 목록, 지오코딩, 역지오코딩,
우편번호 조회를 확인하는 디버그용 패키지입니다. Python 패키지는 FastAPI 백엔드를
제공하고, `web/`에는 같은 API를 보는 Next.js UI가 들어 있습니다.

## 설치

루트 라이브러리와 디버그 UI 패키지를 편집 가능 모드로 함께 설치합니다.

```powershell
python -m pip install -e ".[dev,spatialite]"
python -m pip install -e "debug-ui[dev,spatial]"
```

## 환경 변수

- `KRADDR_GEO_SPATIALITE_PATH`: 사용할 SQLite/SpatiaLite DB 경로
- `VWORLD_API_KEY`: 로컬 결과가 없을 때 asyncio 기반 VWorld 대체 호출에 사용할 API 키
- `VWORLD_DOMAIN`: VWorld API 호출 도메인

## 실행

```powershell
$env:KRADDR_GEO_SPATIALITE_PATH = "F:\dev\python-kraddr-geo\data\juso\kraddr_geo.sqlite"
uvicorn kraddr_geo_debug_api.main:app --app-dir debug-ui/src --host 127.0.0.1 --port 3011
```

또는 패키지 스크립트를 사용할 수 있습니다.

```powershell
kraddr-geo-debug-api
```

## 엔드포인트

- `GET /health`: DB 파일, 포인트/경계 건수, SpatiaLite 로드 상태 확인
- `GET /addresses`: 주소 목록과 검색
- `GET /geocode`: 주소 지오코딩 응답
- `GET /reverse-geocode`: 좌표 기반 역지오코딩 응답
- `GET /postal-codes/{zipcode}`: 우편번호 기반 주소 후보 조회
- `POST /load-jobs`: TXT/ZIP/7Z/SHP 업로드 적재 작업 생성
- `GET /load-jobs`: 최근 적재 작업 목록
- `GET /load-jobs/{job_id}`: 적재 진행률, 로드/스킵 건수, 오류 조회

좌표는 기본적으로 EPSG:5179 기준으로 저장하고, 요청 좌표계가 다르면 `pyproj`로 변환합니다.

`POST /load-jobs`는 `multipart/form-data`를 사용합니다.

- `files`: 여러 개 업로드 가능
- `dataset`: `auto`, `location_summary`, `navigation_building`,
  `navigation_road_section_entrance`, `boundary_shapes`
- `replace`: 같은 자료를 먼저 삭제하고 넣을지 여부

SHP 수동 적재는 `.shp`, `.dbf`, `.shx`를 같은 파일명 줄기로 함께 올리는 방식을
지원합니다. `.prj`, `.cpg` 등 보조 파일도 함께 보존됩니다.

## 웹 UI

```powershell
cd debug-ui/web
npm install
npm run dev
```
