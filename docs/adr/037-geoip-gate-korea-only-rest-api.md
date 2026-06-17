# ADR-037: 외부 IP에서 호출되는 REST API는 대한민국 IP만 허용한다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

## 컨텍스트

본 라이브러리는 행안부 도로명주소·우편번호·내비DB·전자지도 자료와 vworld/kakao/naver fallback을 사용한다. 모두 한국 사용 전제로 약관이 작성되어 있고, 외부 fallback의 호출 한도도 한국 IP 기준이다. REST API 표면을 한국 외 공용 IP에 그대로 노출하면 약관·호출 한도·법적 책임 모두 문제가 된다. ADR-013은 디버그/관리 UI를 사내 내부망 전용으로 두었지만, 일반 `/v1/*` 엔드포인트의 외부 노출 정책은 명문화되지 않았다.

## 결정

REST API 표면은 **외부(공용) IP에서 호출될 때 대한민국 IP만 허용**한다.

1. 적용 대상: `/v1/address/geocode`, `/v1/address/reverse`, `/v1/address/search`, `/v1/address/zipcode`, `/v1/address/pobox`, `/v1/admin/*`, `/v2/*`(T-052 신규).
2. 적용 제외: `/v1/healthz`, `/metrics`(uptime/probe 호환).
3. 내부 사설/loopback IP는 그대로 허용(`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1/128`, `fc00::/7`, `fe80::/10`).
4. 외부 공용 IP는 GeoIP DB(MaxMind GeoLite2 Country 등) 조회로 country code `KR`만 허용.
5. `Settings.geoip_allow_cidrs`/`geoip_deny_cidrs`로 명시 override 가능. 우선순위: `deny > allow > 사설/loopback > KR > 기본 deny`.
6. 구현 위치: FastAPI middleware(`api/middleware/geoip_gate.py`). nginx/reverse proxy layer는 추가 layer로 운영 가능하지만 기본 안전망은 application에서 보장.
7. deny 발생 시 HTTP 403 + 한국어/영어 분리 메시지 + `ops.audit_events(action='geoip.denied', payload_redacted={client_country, path, ...})` 기록. IP는 hash로만 저장(ADR-033).
8. GeoIP DB 부재 시 `geoip_gate_mode`로 동작 선택:
   - `strict`(기본): 외부 IP 전부 deny.
   - `permissive`: 모두 allow + log warning(개발 환경).
   - `off`: gate 비활성화(테스트 전용).
9. `X-Forwarded-For` 처리: `Settings.geoip_trusted_proxies`에 명시된 hop만큼 pop해 실제 client IP 추출. trust 안 된 proxy 뒤의 값은 무시.

## 근거

- 외부 데이터 약관(도로명주소, 우편번호, vworld 등)과 호출 한도가 한국 IP 기준이다. 한국 외 호출은 약관 위반 위험.
- ADR-013은 디버그/관리 UI만 다뤘다. 일반 REST 표면의 외부 노출은 별도 결정 필요.
- 라이브러리 사용자가 `uvicorn kortravelgeo.api.app:app`만 실행해도 외부 차단이 작동해야 한다. application layer 보호가 1차 안전망.
- 사설/loopback 허용으로 사내망/Docker 네트워크는 영향 없음.

## 결과

- T-054에서 middleware + GeoIP settings + audit 연계를 1차 구현했다.
- `ktgctl geoip check <ip>` CLI 진단 helper 추가.
- 운영자는 월 1회 MaxMind license key로 GeoIP DB 갱신.
- `/admin/stats`(T-053)에 KR vs non-KR 요청 분포 시각화.

## 남은 위험

- GeoIP DB는 IP-country 매핑이 100% 정확하지 않다. mobile/CDN IP 갱신 lag.
- `X-Forwarded-For` spoofing — `trusted_proxies` 미설정 시 잘못된 client IP 신뢰.
- 한국 사용자가 외부 VPN/proxy를 통해 접근하면 차단 가능. 운영 공지 필요.
- 본 gate는 application layer다. nginx/firewall layer 차단이 더 빠르고 안전하므로, 본 라이브러리는 "기본 안전망" 위치.
