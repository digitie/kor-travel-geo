# kraddr-geo FastAPI backend

`backend`는 SQLite + SpatiaLite 파일을 읽어 주소 목록, geocoding, reverse geocoding, 우편번호 조회를 제공하는 FastAPI 서버입니다.

## 환경 변수

- `KRADDR_GEO_SPATIALITE_PATH`: 사용할 SQLite/SpatiaLite DB 경로
- `VWORLD_API_KEY`: 로컬 결과가 없을 때 asyncio 기반 VWorld fallback으로 사용할 API 키
- `VWORLD_DOMAIN`: VWorld API 호출 도메인

## 실행

```powershell
$env:KRADDR_GEO_SPATIALITE_PATH = "F:\dev\python-kraddr-geo\data\juso\kraddr_geo.sqlite"
uvicorn kraddr_geo_api.main:app --app-dir backend --host 127.0.0.1 --port 3011
```

WSL에서는 Windows `node.exe`/`npx` 대신 Linux Node를 쓰고, 서버를 `0.0.0.0`에
바인딩하는 편이 안정적입니다. backend + web debug UI 동시 구동 절차는
[`docs/wsl-debug-ui.md`](../docs/wsl-debug-ui.md)에 정리되어 있습니다.

## 엔드포인트

- `GET /health`: DB 파일, 포인트/경계 건수, SpatiaLite 로드 상태 확인
- `GET /addresses`: 주소 목록과 검색
- `GET /geocode`: VWorld 유사 geocoding 응답
- `GET /reverse-geocode`: VWorld 유사 reverse geocoding 응답
- `GET /postal-codes/{zipcode}`: 우편번호 기반 주소 후보 조회
- `POST /load-jobs`: TXT/ZIP/7Z/SHP 업로드 적재 작업 생성
- `GET /load-jobs`: 최근 적재 작업 목록
- `GET /load-jobs/{job_id}`: 적재 progress, 로드/스킵 건수, 오류 조회

좌표는 기본적으로 EPSG:5179 기준으로 저장하고, 요청 좌표계가 다르면 `pyproj`로 변환합니다.

`POST /load-jobs`는 `multipart/form-data`를 사용합니다.

- `files`: 여러 개 업로드 가능
- `dataset`: `auto`, `location_summary`, `navigation_building`,
  `navigation_road_section_entrance`, `boundary_shapes`
- `replace`: 같은 자료를 먼저 삭제하고 넣을지 여부

SHP 수동 적재는 `.shp`, `.dbf`, `.shx`를 같은 파일명 stem으로 함께 올리는 방식을
지원합니다. `.prj`, `.cpg` 등 sidecar도 함께 보존됩니다.
