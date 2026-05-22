# 외부 REST API 키 발급 및 사용

본 문서는 `addr-kr`이 호출하는 외부 OpenAPI 4종(vworld, juso, epost, kakao maps)의 발급 절차, 환경변수 매핑, 호출 예시, 정책을 한 자리에 모은다. 첨부 사양서 §13.3을 기준으로 정리했다.

## 한눈에

| 서비스 | 발급처 | 용도 | 환경변수 | 키 노출 위치 |
|--------|--------|------|----------|--------------|
| vworld OpenAPI | vworld.kr | 지오코딩 폴백, 통합 검색, WMS/WMTS | `ADDR_KR_VWORLD_API_KEY` | 서버측 |
| juso 검색 | business.juso.go.kr | 도로명/지번 주소 검색 폴백 | `ADDR_KR_JUSO_API_KEY` | 서버측 |
| juso 좌표 | business.juso.go.kr (별도 신청 가능) | 주소 → 좌표 변환 폴백 | `ADDR_KR_JUSO_COORD_API_KEY` (없으면 검색 키 재사용) | 서버측 |
| epost 우편번호 다운로드 | data.go.kr (공공데이터포털) | 사서함·다량배달처 ZIP 자동 다운로드 | `ADDR_KR_EPOST_API_KEY` | 서버측 (로더 cron) |
| Kakao Maps JS | developers.kakao.com | 프론트엔드 지도 | `NEXT_PUBLIC_KAKAO_JS_KEY` | 브라우저 (도메인 제한이 보안) |

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
from addr_kr.settings import get_settings

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
    }, headers={"Referer": "https://addr-kr.your-domain.local"})
    data = r.json()
    # response.status: 'OK' / 'NOT_FOUND' / 'ERROR'
```

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

- **발급처**: https://www.data.go.kr (공공데이터포털)
- **데이터셋**: "과학기술정보통신부 우정사업본부_우편번호 다운로드 서비스" → 활용신청 → 즉시 승인 → "개발계정 상세보기"에서 일반 인증키(Encoding/Decoding 2종).
- **인증키 형식**: Encoding된 키와 URL-Decoded 키가 함께 제공. `httpx`의 `params` 인자로 넘기면 Decoded 키를 쓰는 게 안전(httpx가 URL 인코딩 처리).
- **쿼터**: 개발계정 10,000회/일. 우편번호 다운로드는 보통 월 1~수 회 호출이라 충분.
- **응답**: 우편번호 ZIP 파일의 다운로드 URL. 종류 4가지 — 전체/변경분/범위주소/사서함주소.

### 호출 예 (다운로드)

```python
import httpx, xml.etree.ElementTree as ET

# 다운로드 구분: 1=전체, 2=변경분, 3=범위주소, 4=사서함주소
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

> 우편번호 ZIP 본문 인코딩은 EUC-KR과 UTF-8(BOM)이 시점에 따라 섞여 있다. 적재 전 `iconv` 또는 `chardet`으로 표준화하는 단계가 로더에 포함된다.

## Kakao Maps JavaScript SDK (프론트엔드)

- **발급처**: https://developers.kakao.com
- **절차**: 카카오 계정 로그인 → 내 애플리케이션 → 추가 → 앱 키 화면 → JavaScript 키 복사. 플랫폼(Web) 등록에서 사이트 도메인 추가 — 등록하지 않은 도메인에서는 SDK가 거부.
- **키 노출 정책**: JS 키는 본질적으로 브라우저에 노출(`NEXT_PUBLIC_` 접두사로 번들에 포함). 보안은 **도메인 제한**이 담당. 다른 도메인에서 같은 키를 써도 SDK가 reject.
- **권장 분리**: 개발용 키(`localhost:3000`, `127.0.0.1:3000`)와 운영용 키를 다른 애플리케이션으로 분리.
- **쿼터**: Kakao Maps Web은 사실상 무제한. 모바일·서버 키는 별도.

## `.env` 예시

```bash
# .env (백엔드)
ADDR_KR_PG_DSN=postgresql+psycopg://addr:CHANGEME@localhost:5432/addr_kr
ADDR_KR_LOG_FORMAT=json

# 외부 API (모두 옵션. 없으면 폴백·자동다운로드 비활성화)
ADDR_KR_VWORLD_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ADDR_KR_JUSO_API_KEY=devU01TX0FVVEgyMDIxMDExNTAxNTAxMDExMTAzMDM=
ADDR_KR_JUSO_COORD_API_KEY=                # 비워두면 위 키 사용
ADDR_KR_EPOST_API_KEY=urlDecoded+ServiceKey+Value==
```

```bash
# addr-kr-ui/.env.local
NEXT_PUBLIC_KAKAO_JS_KEY=your_kakao_javascript_app_key
ADDR_KR_API_INTERNAL_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=/api/proxy
```

## 외부 API 호출 정책 (재시도·차단·로깅)

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
