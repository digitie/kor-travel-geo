# 외부 REST API 키 발급 및 사용

본 문서는 `kraddr-geo`이 호출하거나 디버그 UI에서 사용하는 외부 API(vworld, juso, epost)의 발급 절차, 환경변수 매핑, 호출 예시, 정책을 한 자리에 모은다. 첨부 사양서 §13.3을 기준으로 정리했다.

## 한눈에

| 서비스 | 발급처 | 용도 | 환경변수 | 키 노출 위치 |
|--------|--------|------|----------|--------------|
| vworld OpenAPI | vworld.kr | 지오코딩 폴백, 통합 검색 | `KRADDR_GEO_VWORLD_API_KEY` | 서버측 |
| vworld WMTS | vworld.kr | 프론트엔드 디버그 지도(MapLibre) | `NEXT_PUBLIC_VWORLD_API_KEY` | 브라우저 (도메인/IP 제한이 보안) |
| juso 검색 | business.juso.go.kr | 도로명/지번 주소 검색 폴백 | `KRADDR_GEO_JUSO_API_KEY` | 서버측 |
| juso 좌표 | business.juso.go.kr (별도 신청 가능) | 주소 → 좌표 변환 폴백 | `KRADDR_GEO_JUSO_COORD_API_KEY` (없으면 검색 키 재사용) | 서버측 |
| epost 우편번호 다운로드 (데이터셋 `15000302`) | data.go.kr (공공데이터포털) | 사서함·다량배달처 ZIP 분기 1회 적재(ADR-009) | `KRADDR_GEO_EPOST_API_KEY` | 서버측 (로더 cron) |

모든 백엔드 키는 `Settings`에서 `SecretStr`로 저장되어 로그·예외 메시지에 노출되지 않는다. 운영에서는 `.env` 권한 600 또는 systemd `EnvironmentFile`, 그것도 안 되면 vault(HashiCorp Vault / sops / age) 사용. Git에 평문으로 커밋 금지 — `pre-commit`에 `detect-secrets` 또는 `gitleaks` 추가 권장.

## vworld OpenAPI

- **발급처**: https://www.vworld.kr/dev/v4api.do
- **절차**: 회원가입 → 마이페이지 → 오픈API 인증키 신청 → 사용 API(주소·검색·WMS 등) 체크 → 사용 URL(Referer/IP) 등록 → 즉시 발급. 인증키 1개에 도메인 최대 5개.
- **분리 권장**: 로컬 개발(`localhost`), 스테이징, 운영을 별도 키로 분리. 한도 침범 시 영향 격리.
- **쿼터**: 일/월 호출 한도. 콘솔에서 확인. 폴백 용도면 충분.
- **주의**: REST 호출은 등록된 Referer/IP만 통과. 서버측 호출 시에도 등록 도메인을 Referer 헤더로 명시하거나 IP 등록 옵션 사용.

### 호출 예 (httpx async)

```python
import httpx
from kraddr.geo.settings import get_settings

settings = get_settings()
async with httpx.AsyncClient(timeout=5.0) as cx:
    r = await cx.get(settings.vworld_url, params={
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs":     "epsg:4326",
        "address": "서울특별시 강남구 테헤란로 152",
        "type":    "road",
        "format":  "json",
        "errorformat": "json",
        "key":     settings.vworld_api_key.get_secret_value(),
    }, headers={"Referer": "https://kraddr-geo.your-domain.local"})
    data = r.json()
    # response.status: 'OK' / 'NOT_FOUND' / 'ERROR'
```

## vworld WMTS + MapLibre (프론트엔드)

`kraddr-geo-ui`의 지도는 Kakao Maps SDK가 아니라 MapLibre GL JS + VWorld WMTS를 사용한다. 지도 타일은 브라우저에서 직접 호출되므로 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용한다. 이 값은 브라우저 번들에 들어가는 공개 키이며 저장소 문서·예시에는 실제 키를 쓰지 않는다.

- **발급처**: 서버측 vworld OpenAPI 키와 동일하게 https://www.vworld.kr/dev/v4api.do
- **권장 분리**: 서버측 폴백 키(`KRADDR_GEO_VWORLD_API_KEY`)와 프론트엔드 WMTS 키(`NEXT_PUBLIC_VWORLD_API_KEY`)를 분리한다. 로컬 개발용 키에는 `localhost:3000`, `127.0.0.1:3000`만 등록하고 운영 키에는 내부망 도메인만 등록한다.
- **사용 레이어**: 기본은 `Base`. 필요하면 `gray`, `midnight`, `Hybrid`, `Satellite`를 `CoordinateMap.layerType`으로 선택한다.
- **타일 URL 규칙**: `https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{z}/{y}/{x}.{ext}`. `Base`/`gray`/`midnight`/`Hybrid`는 `png`, `Satellite`는 `jpeg`. UI option 이름 `gray`는 VWorld WMTS 요청에서는 `white` layer로 변환한다.
- **zoom 한계**: `Base`/`gray`/`midnight`는 z19까지, `Hybrid`/`Satellite`는 z18까지만 요청한다. 상한을 넘긴 tile 404는 운영 장애로 보지 않고 MapLibre 컴포넌트에서 transient error로 다룬다.
- **attribution**: MapLibre raster source의 attribution은 `공간정보 오픈플랫폼 브이월드`로 표기한다. 운영자는 VWorld 최신 이용약관에서 요구 표기가 바뀌었는지 배포 전 확인한다.
- **소스 코드 위치**: `kraddr-geo-ui/lib/vworld.ts`는 `maplibre-vworld` helper를 재수출하고, `components/vworld/LazyCoordinateMap.tsx`가 Next.js dynamic import, `components/vworld/CoordinateMap.tsx`가 click/marker/fallback/error 처리를 담당한다.
- **CSP 주의**: 현재 UI는 CSP를 강제하지 않지만, 향후 도입하면 `connect-src`와 `img-src`에 `https://api.vworld.kr`를 반드시 포함한다.
- **키 제한·회전**: `NEXT_PUBLIC_VWORLD_API_KEY`는 타일 URL path에 노출된다. 도메인/referrer 제한이 WMTS에 실제 적용되는지 VWorld 콘솔과 운영 환경에서 확인하고, 의심 노출 또는 제한 미적용이 확인되면 키를 회수·재발급한다.

### `digitie/maplibre-vworld-js`와의 관계

디버그 UI는 `digitie/maplibre-vworld-js`를 실제 package dependency로 사용한다. dependency를 변경할 때마다 최신 `main` 또는 stable release를 확인하고, 검증된 최신 버전으로 고정한다. 현재 `kraddr-geo-ui`는 `maplibre-vworld`를 `git+https://github.com/digitie/maplibre-vworld-js.git#1a28b1099ab6c9c03e892e469974aee8c07deda1`로 고정하고, `zod ^4.4.3`을 직접 의존성으로 둔다. PR #6/#7 merge 이후 GitHub install 결과물에는 `dist/`, package `exports`, `types`, `style.css`가 포함되어 있고, PR #9 이후 click/error/flyTo hook과 tile error helper를 제공한다. 최신 redaction helper 이름은 `redactVWorldUrl()`이며 redaction 표기는 `***`다. UI 내부에서는 기존 컴포넌트 import를 깨지 않기 위해 `redactVWorldTileUrl` alias로 재수출한다.

다만 `VWorldMap` 컴포넌트 전체 대체는 단계적으로 진행한다. 현재 디버그 UI는 지도 표시 외에 click callback, key 미설정 fallback, transient tile error redaction/overlay, marker 즉시 이동, SSR-safe dynamic wrapper를 보장해야 한다. 범용 지도 primitive와 helper는 upstream API로 맞추되, geocode/reverse 입력 연결, API 응답 overlay, 정합성/성능/적재 상태 표시, 이 프로젝트 fallback 문구와 임계치는 `kraddr-geo-ui` domain wrapper에 남긴다.

문제 발생 시 원칙:

- `maplibre-vworld-js`의 `exports`, `files`, `dist`, type declaration 누락으로 생기는 build 실패는 upstream 저장소를 수정한다.
- VWorld layer helper, MapLibre marker/click/cluster, CSS import, React/Next.js 타입 호환성처럼 재사용 가능한 문제는 `kraddr-geo-ui` 전용 workaround에 묻지 않고 upstream PR/커밋으로 보강한다.
- 주소 지오코딩 디버그 화면과 운영 콘솔에만 필요한 상태 연결, overlay, fallback 문구, 임계치는 이 저장소에서 구현한다.
- `kraddr-geo-ui`에서 upstream SHA를 바꿀 때는 `npm ci` 직후 `lint`, `type-check`, `test`, `build`를 모두 확인한다.
- 후속 PR에서는 click callback, marker 제어, tile error hook, fallback surface, SSR-safe 사용 방식 중 범용화 가능한 부분을 `maplibre-vworld-js`에 맞추고, 프로젝트 특화 부분은 wrapper 경계로 남긴다.

## juso (도로명주소 안내시스템)

- **발급처**: https://business.juso.go.kr (사업자 신청 권장). 일반 무료는 https://www.juso.go.kr/addrlink/devAddrLinkRequestWrite.do
- **절차**: 회원가입 → API 신청서(이용 형태·사용 도메인) → 보통 1영업일 이내 승인 → 마이페이지에서 키. 도메인 추가는 재제출.
- **두 가지 API**:
  - 도로명주소 검색 — 무료 즉시 사용
  - 좌표 제공 — 별도 승인 필요한 경우. `Settings.juso_coord_api_key`를 분리해 둔 이유. 비워두면 검색 키 재사용.
- **쿼터**: 일반 키 약 30,000회/일. 사업자 키는 신청 시 상향 가능. 검색과 좌표 변환 쿼터 분리.

### 호출 예

```python
# 도로명주소 검색
async with httpx.AsyncClient() as cx:
    r = await cx.get(settings.juso_search_url, params={
        "confmKey":     settings.juso_api_key.get_secret_value(),
        "currentPage":  1,
        "countPerPage": 10,
        "keyword":      "테헤란로 152",
        "resultType":   "json",
    })
    items = r.json()["results"]["juso"]
    # items[].roadAddr, items[].jibunAddr, items[].bdMgtSn, items[].admCd, items[].rnMgtSn, ...

# 좌표 변환 (검색에서 받은 admCd, rnMgtSn, udrtYn, buldMnnm, buldSlno 필요)
async with httpx.AsyncClient() as cx:
    r = await cx.get(settings.juso_coord_url, params={
        "confmKey":  (settings.juso_coord_api_key or settings.juso_api_key).get_secret_value(),
        "admCd":     "1168010100",
        "rnMgtSn":   "116803122001",
        "udrtYn":    "0",
        "buldMnnm":  152,
        "buldSlno":  0,
        "resultType": "json",
    })
```

## epost (우편번호 다운로드 OpenAPI)

- **데이터셋**: `15000302` — "과학기술정보통신부 우정사업본부_우편번호 다운로드 서비스" (https://www.data.go.kr/data/15000302/openapi.do)
- **발급처**: https://www.data.go.kr (공공데이터포털) → 활용신청 → 즉시 승인 → "개발계정 상세보기"에서 일반 인증키(Encoding/Decoding 2종).
- **인증키 형식**: Encoding된 키와 URL-Decoded 키가 함께 제공. `httpx`의 `params` 인자로 넘기면 Decoded 키를 쓰는 게 안전(httpx가 URL 인코딩 처리).
- **쿼터**: 개발계정 10,000회/일. 갱신 호출은 분기당 4종 × 1회 정도라 충분.
- **응답**: 우편번호 ZIP 파일의 다운로드 URL을 담은 XML(`fileLocplc` 노드). 매칭 결과를 직접 주지 않으므로 ZIP을 받아 로컬 DB에 적재한 뒤 매칭한다(ADR-009).

### `downloadKnd` 4종

| 값 | 종류 | 본 프로젝트 적재 대상 |
|----|------|----------------------|
| 1 | 전체 | `postal_pobox`, `postal_bulk_delivery`(전량 갱신 시) |
| 2 | 변경분 | 사용하지 않음 — 분기 1회 전체 갱신만 운영(ADR-009) |
| 3 | 범위주소 | (선택) 보조 우편번호 검증용 |
| 4 | 사서함주소 | `postal_pobox` 정합성 보강 |

본 프로젝트는 **분기당 1회 `downloadKnd=1`(전체)** 호출로 운영한다. 변경분(`2`)을 누적 추적하지 않는 이유는 (a) 우편번호 데이터셋이 분기 단위로도 충분히 안정적이고, (b) 전체 ZIP 적재 후 `postal_*` 테이블을 TRUNCATE → INSERT 하는 편이 변경분 머지보다 단순·안전하기 때문이다(ADR-009 후속).

### 호출 예 (다운로드)

```python
import httpx, xml.etree.ElementTree as ET

# 본 프로젝트 표준: 분기 1회, downloadKnd=1 (전체)
async def fetch_zip_url(division: int = 1) -> str:
    async with httpx.AsyncClient(timeout=15.0) as cx:
        r = await cx.get(settings.epost_download_url, params={
            "serviceKey": settings.epost_api_key.get_secret_value(),
            "downloadKnd": division,
        })
        root = ET.fromstring(r.text)
        return root.findtext(".//fileLocplc") or ""

async def download_zip(url: str, dst: str) -> None:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as cx:
        async with cx.stream("GET", url) as r:
            with open(dst, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
```

> 우편번호 ZIP 본문 인코딩은 EUC-KR과 UTF-8(BOM)이 시점에 따라 섞여 있다. 적재 전 `iconv` 또는 `chardet`으로 표준화하는 단계가 로더에 포함된다(T-017 `pobox_loader.py`, `bulk_loader.py`).

### 매칭 흐름

본 API는 실시간 우편번호 조회 API가 아니라 **ZIP 메타 다운로드 서비스**다. 우편번호 매칭은 로컬 DB로 처리한다(ADR-009).

```
[분기 cron / 수동 트리거]
  ↓
GET /downloadAreaCodeService?serviceKey=...&downloadKnd=1
  ↓
XML 응답에서 fileLocplc(ZIP URL) 추출
  ↓
ZIP 스트리밍 다운로드 → 인코딩 표준화(EUC-KR/UTF-8)
  ↓
postal_pobox / postal_bulk_delivery TRUNCATE → INSERT
  ↓
docs/reverse-geocoding.md §우편번호 lookup 4단계 우선순위에서 사용
```

### 도입하지 않는 API

- **`15056971` (우정사업본부_우편번호 정보조회, 실시간 lookup)** — 본 프로젝트는 분기 ZIP 적재 + 로컬 DB 매칭으로 충분하다고 결정했다(ADR-009). 실시간 lookup이 필요해지는 시점에 새 ADR로 재검토.

## `.env` 예시

```bash
# .env (백엔드)
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:CHANGEME@localhost:5432/kraddr.geo
KRADDR_GEO_LOG_FORMAT=json

# 외부 API (모두 옵션. 없으면 폴백·자동다운로드 비활성화)
KRADDR_GEO_VWORLD_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
KRADDR_GEO_JUSO_API_KEY=devU01TX0FVVEgyMDIxMDExNTAxNTAxMDExMTAzMDM=
KRADDR_GEO_JUSO_COORD_API_KEY=                # 비워두면 위 키 사용
KRADDR_GEO_EPOST_API_KEY=urlDecoded+ServiceKey+Value==
```

```bash
# kraddr-geo-ui/.env.local
NEXT_PUBLIC_VWORLD_API_KEY=your_vworld_api_key
KRADDR_GEO_API_INTERNAL_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=/api/proxy
```

## 외부 API 호출 정책 (재시도·차단·로깅)

- **구현 위치**: `src/kraddr/geo/infra/external_api.py`. `AsyncAddressClient.geocode(..., fallback="api")`에서 로컬 DB 결과가 `NOT_FOUND`일 때만 호출한다. core 계층은 HTTP와 API key를 전혀 알지 않는다.
- **호출 순서**: vworld 주소 좌표 API를 먼저 시도하고, 키가 없거나 결과가 없으면 juso 검색 API + juso 좌표 API를 시도한다. 두 공급자 모두 실패하거나 키가 없으면 로컬 `NOT_FOUND` 응답을 그대로 반환한다.
- **응답 매핑**: 외부 응답도 `GeocodeResponse`로 변환한다. 공급자 출처는 `x_extension.source`에만 `api_vworld` 또는 `api_juso`로 남긴다. vworld 호환 최상위 응답 구조는 바꾸지 않는다(ADR-003).
- **재시도**: `tenacity`로 5xx와 timeout만 3회 지수 backoff. 4xx는 즉시 실패(키 오류, 입력 오류).
- **회로차단**: 같은 외부 서비스에 1분 내 5회 연속 실패하면 60초 동안 폴백 호출 차단(로컬만 응답). `httpx` + 자체 카운터 또는 `purgatory`.
- **쿼터 보호**: 일 한도의 80%에 도달하면 Prometheus 알람. 90% 초과 시 자동으로 polling 인터벌 늘리거나 폴백 비활성화.
- **로그**: 호출 1건당 한 줄 structlog — 서비스명·응답 시간·상태·응답 크기. 키 자체는 절대 로그에 남기지 않음(`SecretStr`은 repr이 `**********`).

### 재시도 패턴

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2.0),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True,
)
async def call_vworld_geocode(address: str) -> dict:
    async with httpx.AsyncClient(timeout=3.0) as cx:
        r = await cx.get(settings.vworld_url, params={...})
        r.raise_for_status()
        return r.json()
```
