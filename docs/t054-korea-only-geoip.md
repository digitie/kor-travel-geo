# T-054: 한국 IP 외부 접근 차단 (Geo-IP gate)

## 상태

- 상태: 설계 (구현 전)
- 대상 브랜치: `agent/<agent>-t054-*`
- 관련 ADR: ADR-037(예정)
- 사용자 RFC: 2026-05-27 — "한국에서만 쓸 수 있도록 (외부 IP에서 접속하는 API 접근은 한국에서만 쓸 수 있도록)."

## 목적

`python-kraddr-geo`는 행안부 도로명주소·우편번호·내비게이션DB·전자지도 데이터를 사용한다. 이 자료는 한국 사용 전제로 약관이 작성됐고, vworld/kakao/naver fallback도 한국 IP 기준 한도/약관이 있다. 따라서 본 라이브러리의 REST API 표면은 **외부(공용) IP에서 호출될 때 대한민국 국가로 식별되는 IP만 허용**해야 한다.

내부망/사설 IP에서의 호출은 그대로 허용한다. ADR-013(사내 내부망 전용)과 일관.

## 적용 표면

| 표면 | gate 적용 여부 | 비고 |
|------|----------------|------|
| `POST /v1/geocode`, `POST /v1/reverse`, `GET /v1/search`, `GET /v1/zipcode`, `GET /v1/pobox` | 적용 | 외부 자료 사용 |
| `POST /v2/geocode`, `/v2/reverse`, `/v2/search` (T-052) | 적용 | 외부 자료 사용 |
| `/v1/admin/*` (관리 표면) | 적용(강력) | 내부망 가정. 외부 KR IP라도 admin은 별도 allowlist 권장 |
| `/healthz`, `/metrics` | 미적용 | LB/uptime probe 호환 |
| `/openapi.json`, `/docs`, `/redoc` | 적용 가능(선택) | 외부 KR만 허용 |
| `kraddr-geo` CLI | 미적용 | local execution |
| `AsyncAddressClient` (라이브러리 직접 호출) | 미적용 | local execution |

## IP 분류 기준

```text
1. private/loopback (allow)
   - IPv4: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8
   - IPv6: ::1/128, fc00::/7 (ULA), fe80::/10 (link-local)
2. Korea public (allow)
   - GeoIP DB의 country code = 'KR'
3. allowlist (allow)
   - Settings.geoip_allow_cidrs 명시 IP/CIDR
4. denylist (deny, override)
   - Settings.geoip_deny_cidrs 명시 IP/CIDR
5. 그 외 (deny)
```

평가 순서: deny > allow > 사설/loopback > KR > deny default.

## 구현 옵션 비교

### Option A — FastAPI middleware (권장)

`src/kraddr/geo/api/middleware/geoip_gate.py` 신규.

```python
class KoreaOnlyMiddleware:
    def __init__(self, app, *, settings: GeoIpSettings, reader: GeoIpReader):
        self.app = app
        self.settings = settings
        self.reader = reader

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if self._is_open_path(path):
            return await self.app(scope, receive, send)
        client_ip = self._client_ip(scope)
        decision = classify_ip(
            client_ip,
            reader=self.reader,
            allow_cidrs=self.settings.geoip_allow_cidrs,
            deny_cidrs=self.settings.geoip_deny_cidrs,
        )
        if decision.action != "allow":
            await self._deny(send, decision)
            return
        await self.app(scope, receive, send)
```

- 장점: 코드 안에 정책 명확, audit_event 기록 가능, `/healthz`/`/metrics` 같은 오픈 path 단일 위치에서 통제.
- 단점: middleware에서 GeoIP DB 메모리 사용. `KRADDR_GEO_GEOIP_DB_PATH` 미설정 시 fallback 정책 필요.

### Option B — nginx/reverse proxy layer

`ngx_http_geoip2_module` 또는 Cloudflare `cf-ipcountry` header.

- 장점: 앱 부담 0.
- 단점: 운영자가 nginx 설정을 추가로 관리. 본 라이브러리 단독 사용자(직접 uvicorn)는 보호 받지 못함.

### 결정

**Option A를 기본으로 한다.** nginx 등 reverse proxy가 있으면 추가 layer로 운영 가능하지만, 라이브러리 사용자가 `uvicorn kraddr.geo.api.app:app`만 실행해도 KR 외 차단이 작동해야 한다.

## GeoIP DB

### 채택

MaxMind GeoLite2 Country DB(무료) 또는 IP2Location LITE.

- `KRADDR_GEO_GEOIP_DB_PATH`: 로컬 `.mmdb` 또는 `.bin` 파일 경로. 기본 `data/geoip/GeoLite2-Country.mmdb`.
- 갱신: 운영자가 월 1회 cron으로 download. 본 라이브러리는 자동 download 안 함(라이선스 키 required, 운영자 책임).
- DB 부재 시 정책:
  - `geoip_gate_mode = "strict"`: 모든 외부 IP deny (보수적, 기본값).
  - `geoip_gate_mode = "permissive"`: 모든 IP allow + log warning (개발 환경).
  - `geoip_gate_mode = "off"`: gate 자체 비활성화.

### 캐시

같은 IP의 lookup은 LRU cache(`functools.lru_cache(maxsize=10_000)`)로 메모리 캐시. GeoIP DB가 disk 기반이라 in-process 호출 cost는 작지만 hot path latency 절약.

## settings

```python
class GeoIpSettings(BaseModel):
    geoip_db_path: Path | None = None
    geoip_gate_mode: Literal["strict","permissive","off"] = "strict"
    geoip_allow_cidrs: tuple[IPv4Network | IPv6Network, ...] = ()
    geoip_deny_cidrs: tuple[IPv4Network | IPv6Network, ...] = ()
    geoip_open_paths: tuple[str, ...] = ("/healthz","/metrics")
    geoip_trusted_proxies: tuple[IPv4Network | IPv6Network, ...] = ()
    geoip_audit_denials: bool = True
```

`geoip_trusted_proxies`: nginx/Cloudflare 같은 LB 뒤에 있을 때 `X-Forwarded-For` 끝에서부터 trusted hop 만큼 pop해 진짜 client IP 추출. trust 안 된 proxy 뒤의 값은 무시.

`geoip_audit_denials`: deny 발생 시 `ops.audit_events`에 `action="geoip.denied"` 자동 기록.

## 응답

deny 시 HTTP 403 + 한국어/영어 message 분리:

```json
{
  "code": "E_FORBIDDEN_REGION",
  "message": "이 서비스는 대한민국 IP에서만 호출할 수 있습니다.",
  "message_en": "This service is restricted to requests from South Korea.",
  "client_country": "US",
  "trace_id": "..."
}
```

`code`는 `dto/errors.py`에 enum으로 등록.

## audit 연계 (T-049)

deny 발생 시 `ops.audit_events`에 다음을 기록(payload는 redacted):

```json
{
  "action": "geoip.denied",
  "outcome": "denied",
  "actor_type": "api",
  "client_ip_hash": "...",  // SHA256 of client_ip, NOT raw IP
  "user_agent_hash": "...",
  "payload_redacted": {
    "path": "/v1/geocode",
    "method": "POST",
    "client_country": "US",
    "reason": "non_kr_public_ip"
  }
}
```

IP 원문 평문 저장 금지(ADR-033). hash만 저장.

## CLI/도구

- `kraddr-geo geoip check <ip>`: 디버그용. 주어진 IP가 어떤 분류로 평가되는지 출력.
- `kraddr-geo geoip stats`: 최근 deny 통계.

## 검증

- 단위 테스트: classify_ip(sample IPv4/IPv6, allow/deny cidrs) → 예상 결정.
- middleware 통합 테스트: FastAPI TestClient + mock GeoIP reader.
- `/healthz`, `/metrics`는 deny 대상에서 제외되는지 확인.
- DB 부재 + `strict` 모드에서 외부 IP 차단.
- trusted_proxies 환경에서 `X-Forwarded-For` 끝에서부터 hop 만큼 pop하는지 확인.
- 한국 KR IP 샘플(SK Telecom/KT/LG U+/AWS Seoul) → allow.
- 외부 IP 샘플(US/CN/JP) → deny.
- ops.audit_events에 `geoip.denied` row 생성.

## 운영 가이드

- 운영자는 월 1회 GeoIP DB 갱신(`MaxMind` license key).
- 사내 NAT 뒤에 있는 운영자가 KR이 아닌 region으로 분류되면 `geoip_allow_cidrs`에 추가.
- VPN/proxy 환경에서 KR 사용자가 외부 IP로 보이면 운영자 책임.
- 약관 변경 시(예: 일부 지원 region 추가) `geoip_gate_mode="permissive"` + denylist 운영 가능.

## 남은 위험

- GeoIP DB는 IP-to-country 매핑이 100% 정확하지 않다. 모바일/CDN IP는 갱신 lag 가능.
- IPv6은 GeoIP DB coverage가 IPv4보다 떨어질 수 있다.
- `X-Forwarded-For` spoofing 위험: `geoip_trusted_proxies` 미설정 시 client IP를 잘못 신뢰할 수 있다. 운영자가 LB 뒤 실제 trusted hop 수를 명시해야 한다.
- 본 gate는 application layer다. nginx/firewall layer에서 차단하면 더 빠르고 안전하므로, 본 라이브러리는 "기본 안전망" 위치로 둔다.

## 관련 ADR/Task

- ADR-013: 디버그/관리 UI는 사내 내부망 전용.
- ADR-037(예정): 한국 IP gate 정책.
- T-049: ops.audit_events에 deny 기록.
- T-053: `/admin/stats`에 KR vs non-KR 요청 분포 시각화.
