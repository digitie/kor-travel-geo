# python-kraddr-geo

`python-kraddr-geo`는 행정안전부/Juso 주소 자료를 내려받고, 로컬 SQLite + SpatiaLite 데이터베이스로 정리해 지오코딩/역지오코딩 API를 제공하는 Python 라이브러리입니다.

목표는 VWorld 지오/역지오 API와 최대한 비슷한 호출 흐름을 제공하면서도, 로컬 데이터가 충분할 때는 외부 API 없이 빠르게 결과를 돌려주는 것입니다.

## 주요 기능

- 도로명주소 파일 다운로드 및 파싱
- 위치정보요약DB 출입구 좌표 적재
- 내비게이션용DB 건물/출입구 좌표 적재
- 구역의 도형 ZIP 적재와 행정구역 경계 보조 조회
- SQLite + SpatiaLite 기반 공간 저장소
- 우편번호에서 도로명주소/법정동코드 후보 조회
- 주소 지오코딩 DTO 기반 `get_coord`, `get_address` 호출
- 로컬 결과가 없을 때 `python-vworld-api`의 asyncio 클라이언트를 통한 대체 호출
- FastAPI 백엔드와 Next.js 주소 브라우저
- 웹/API 기반 TXT, ZIP, 7Z, SHP 수동 업로드 적재와 진행률 조회

## 설치

```powershell
python -m pip install -e ".[dev,spatialite]"
```

선택 데이터 처리에 필요한 패키지는 `spatialite` extra에 포함되어 있습니다. SpatiaLite 확장을 로드할 수 없는 환경에서도 기본 `x`, `y`, WKT/WKB 컬럼과 B-tree 인덱스로 동작합니다.

## 문서 언어

이 저장소의 Markdown/RST 문서는 한국어로 작성합니다. 공식 API 필드명, 코드 식별자, 명령어, URL, 패키지명처럼 그대로 보존해야 하는 값만 원문을 유지합니다.

## 데이터 적재

현재 권장 적재 순서는 다음과 같습니다.

1. 위치정보요약DB: 건물 출입구 좌표의 주 자료
2. 내비게이션용DB: 건물 중심/대표 출입구와 도로구간 출입구 보조 자료
3. 구역의 도형: 행정구역 경계와 교차검증 자료
4. 기존 도로명주소/관련지번 SQLite: 주소 속성 보완 자료

```python
from pathlib import Path

from kraddr.geo import SpatialiteAddressStore

store = SpatialiteAddressStore("data/juso/kraddr_geo.sqlite")
store.load_location_summary_archive(Path("data/juso/202604_위치정보요약DB_전체분.zip"))
store.load_boundary_zips(sorted(Path("data/juso/구역의 도형").glob("*.zip")))
```

내비게이션용DB의 `.7z` 파일은 `py7zr`가 설치되어 있으면 바로 읽을 수 있습니다. 이미 TXT로 추출한 파일도 동일한 파서로 처리할 수 있습니다.

## API 예시

```python
from kraddr.geo import (
    PostalCodeLookupRequest,
    SpatialiteAddressStore,
    AddressGeocodeRequest,
    AddressReverseGeocodeRequest,
)

with SpatialiteAddressStore("data/juso/kraddr_geo.sqlite") as store:
    coord = store.get_coord(AddressGeocodeRequest(query="부산광역시 중구 초량상로 1-2"))
    address = store.get_address(AddressReverseGeocodeRequest(x=1139887.36, y=1680774.72))
    postal = store.lookup_postal_code(PostalCodeLookupRequest(zipNo="48910"))
```

동기 `get_coord`, `get_address`는 로컬 SQLite/SpatiaLite 조회만 수행합니다.
VWorld 대체 호출을 쓰려면 API 키를 넘기고 비동기 `aget_coord`, `aget_address`를 호출합니다.

```python
import asyncio

from kraddr.geo import SpatialiteAddressStore


async def main() -> None:
    async with SpatialiteAddressStore(
        "data/juso/kraddr_geo.sqlite",
        vworld_api_key="...",
        vworld_domain="...",
    ) as store:
        coord = await store.aget_coord({"query": "부산광역시 중구 초량상로 1-2"})
        address = await store.aget_address({"x": 127.1, "y": 37.4, "crs": "EPSG:4326"})


asyncio.run(main())
```

## 디버그 UI

FastAPI 백엔드와 Next.js 웹 UI는 디버그 목적이므로 `debug-ui/`의 별도 Python
패키지로 분리되어 있습니다.

```powershell
$env:KRADDR_GEO_SPATIALITE_PATH = "F:\dev\python-kraddr-geo\data\juso\kraddr_geo.sqlite"
uvicorn kraddr_geo_debug_api.main:app --app-dir debug-ui/src --host 127.0.0.1 --port 3011
```

웹은 `debug-ui/web/`의 Next.js 앱입니다. 기본 API 주소는 `http://127.0.0.1:3011`입니다.

수동 적재 API는 `POST /load-jobs`를 사용합니다. 여러 파일을 `files` 필드로 올리고,
`dataset=auto`로 두면 파일명과 ZIP 내부 구조를 기준으로 위치정보요약DB,
내비게이션용DB, 구역 도형을 판별합니다. SHP는 같은 stem의 `.shp/.dbf/.shx/.prj/.cpg`
파일을 함께 올리면 임시 ZIP으로 묶어 경계 로더에 전달합니다. 작업 상태는
`GET /load-jobs/{job_id}`에서 확인합니다.

## 테스트

```powershell
python -m pytest -q
python -m ruff check .
cd debug-ui/web
npm run lint
npm run test
npm run build
```

실제 대용량 자료 적재 검증은 `data/juso`의 ZIP/TXT 자료가 있는 로컬 환경에서 별도 스모크 스크립트로 수행합니다. 일반 테스트는 작은 고정 샘플 중심으로 빠르게 유지합니다.
